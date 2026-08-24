-- int_coicop_classified
-- COICOP division classification ladder (see COICOP_MAPPING.md and AUDIT_REPORT.md).
-- One row per (item_id, store_slug) from int_prices_cleaned.
--
-- Resolution order (first match wins):
--   1. override       -> coicop_override seed + silver.coicop_override_manual,
--                        split into two tiers:
--                        a) exact/per-store: barcode, product_key, or name rules
--                           explicitly tagged to this store (human authority)
--                        b) global name-substring rules (store_slug null/empty)
--   2. store_purity   -> single-division stores (pharmacies=06, real estate=04,
--                        hotels=11, transit/fuel=07, telecom=08). Enforced ABOVE
--                        all automatic signals; only exact/per-store human
--                        overrides beat it.
--   3. gemini_ai      -> silver.dim_coicop_ai_cache (cached classifications with normalized key)
--   4. exceptions     -> deterministic trap regex (COOKING WINE -> 01, medical masks -> 06, etc.)
--   5. keyword STRONG -> dbt seed coicop_keywords.csv rows with priority < 300
--                        (high-precision blocks: clothing, cosmetics, alcohol,
--                        household...). Above category_map because scrapers
--                        often collapse unrelated shelves into generic native
--                        categories.
--   6. category_map   -> silver.coicop_category_map (store native category -> division)
--   7. keyword WEAK   -> seed rows with priority >= 300 (broad food vocabulary),
--                        only fires when the store taxonomy misses
--   8. store_default  -> hard per-store rules + coicop_store_defaults seed
--   9. UNCLASSIFIED / REVIEW -> fallback for triage & Gemini AI
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['item_id', 'store_slug'],
    on_schema_change='append_new_columns',
    post_hook=[
        "CREATE INDEX IF NOT EXISTS idx_int_coicop_item_store ON {{ this }} (item_id, store_slug)",
        "CREATE INDEX IF NOT EXISTS idx_int_coicop_division ON {{ this }} (coicop_division)"
    ]
) }}

with items as (
    -- DAILY-SCOPED: classify ONLY the products present in the current run's
    -- scrape (Airflow passes --vars '{"ds": "YYYY-MM-DD"}'; manual dbt runs
    -- fall back to the latest scrape_date). Historical rows already stored in
    -- this table are kept as-is, so downstream fact joins and index history
    -- remain stable.
    -- ONE-TIME FULL RECOMPUTE after a rule change (pre-production rescue):
    --   dbt run --full-refresh --select int_coicop_classified \
    --     --vars '{"reclassify_all": true}'
    -- This scans every product pair ever scraped using current rules, then
    -- rebuild downstream facts: dbt run --full-refresh --select fct_daily_prices.
    select distinct
        p.item_id::text as item_id,
        p.store_slug,
        ci.canonical_name,
        ci.barcode,
        p.category_native,
        p.item_id::text as product_key,
        null::numeric as price_khr
    from (
        select distinct item_id, store_slug, category_native
        from {{ ref('int_prices_cleaned') }}
        where item_id is not null
          {% if var('reclassify_all', false) %}
          {% elif var('ds', none) %}
          and scrape_date = '{{ var("ds") }}'::date
          {% else %}
          and scrape_date = (select max(scrape_date) from {{ ref('int_prices_cleaned') }})
          {% endif %}
    ) p
    join {{ source('silver', 'canonical_items') }} ci
        on ci.item_id::text = p.item_id::text
    {% if is_incremental() %}
    -- Self-healing: recompute every pair on each run EXCEPT pairs already
    -- resolved by a human override. The previous guard skipped ANY existing
    -- pair, so a keyword-guessed label was locked in forever and never
    -- upgraded when the Gemini cache, seeds, or regex rules improved.
    -- Combined with incremental_strategy='delete+insert', recomputed rows
    -- replace their stale versions. Human overrides stay frozen by design;
    -- `dbt run --full-refresh --select int_coicop_classified` resets all.
    where not exists (
        select 1 from {{ this }} t
        where t.item_id = p.item_id::text
          and t.store_slug = p.store_slug
          and t.coicop_method = 'override'
    )
    {% endif %}
),
trap_divisions as (
    select
        i.item_id,
        i.store_slug,
        case
            -- 0. Personal-care products are never food, whatever ingredient
            --    words their names contain (lemongrass/kaffir-lime shampoo,
            --    coconut-water shampoo, almond soap...). NULL lets lower
            --    tiers decide; strong-12 keywords classify them correctly.
            when i.canonical_name ~* '(shampoo|conditioner|hair mask|body wash|shower gel|shower cream|shower foam|bubble bath|facial cleanser|face wash|bar soap|hand soap|toothpaste|mouthwash)' then null
            -- 1. Medical / protective masks -> 06 Health (MUST precede cosmetics)
            -- AEON carve-out: masks sold at supermarkets are hygiene goods (12), not pharmacy health
            when i.canonical_name ~* '(protecting mask|protective mask|surgical mask|medical mask|earloop|ear loop|earlooped|kn95|n95|ffp2|ffp3|melt[- ]?blown)' then
                case when i.store_slug in ('aeon', 'aeon3') then '12' else '06' end
            -- 2. Industrial / tool safety masks -> 05 Furnishings & maintenance
            when i.canonical_name ~* '(gas mask|dust mask|respirator mask)' then '05'
            -- 3. School / office tape -> 10 Education
            when i.canonical_name ~* 'masking tape' then '10'
            -- 4. High-priority deterministic exception traps
            when i.canonical_name ~* 'cooking wine' then '01'
            when i.canonical_name ~* '\m(somersby cider|somersby|wolf blass|martell|ballantine|ballantine`s|chivas|johnnie walker|hoegaarden|sapporo|shochu|remy martin|hennessy|glenfiddich|macallan|jack daniel|jim beam|smirnoff|absolut|bacardi|captain morgan|tanqueray|bombay sapphire|jagermeister|baileys|kahlua|aperol|campari|bottega|limoncino|mouton cadet|anchor ultra|kirishima)\M'
                 and i.canonical_name !~* '(sauce|marinade|bourguignon|braised|vinegar)' then '02'
            when i.canonical_name ~* '\m(rohto|tiger balm|kwan loong|naga balm|bow balm|eye drops?|eyedrops|medicated plaster|cooling plaster)\M' then '06'
            when i.canonical_name ~* '\m(bio-oil|bio oil|hadalabo|cetaphil|saforelle|klorane|old spice|hair serum|facial serum|ambient spray|air freshener)\M'
                 and i.canonical_name !~* '(cookie|biscuit|candy|snack|tea|drink)' then '12'
            when i.canonical_name ~* 'tvhc slipper' then '03'
            when i.canonical_name ~* 'lix floor cleaner' then '05'
            when i.canonical_name ~* 'tv coffee filter' then '05'
            when i.canonical_name ~* 'green onion slicer' then '05'
            when i.canonical_name ~* 'little trees' then '05'
            when i.canonical_name ~* 'my-ring notes' then '09'
            when i.canonical_name ~* 'wakame mixed rice with salmon' then '01'
            when i.canonical_name ~* 'spicy beef hot pot' then '01'
            when i.canonical_name ~* '(beef sparerib|spareribs?|bolognese spaghetti|campagna spaghetti|spaghetti|pasta|butter cookies|candy necklace|pringles)' then '01'
            when i.canonical_name ~* 'sunplay skin aqua' then '12'
            when i.canonical_name ~* 'lipice' then '12'
            -- 5. Health & medical services traps
            when i.canonical_name ~* '\mhospital\M' then '06'
            when i.canonical_name ~* '\mclinic\M'
                 and i.canonical_name !~* '(shampoo|treatment|cream|serum|tonic|toothpaste|hair|skin|face|beauty|cosmetic|makeup|dental|oil|soap)' then '06'
            when i.canonical_name ~* '\mdoctor\M'
                 and i.canonical_name !~* '(playmobil|toy|set|bag|car|drink|energy|tote|mini|gift|costume)' then '06'
            when i.canonical_name ~* 'medical' and i.canonical_name ~* '(visit|consultation|checkup|examination|fee)' then '06'
            when i.canonical_name ~* 'dental' and i.canonical_name ~* '(visit|cleaning|filling|extraction|whitening)' then '06'
            when i.canonical_name ~* 'eye test' or i.canonical_name ~* 'eye exam' then '06'
            when i.canonical_name ~* 'contact lens' or i.canonical_name ~* 'lens solution' then '06'
            when i.canonical_name ~* '(ritex|durex|sagami|okamoto|\mcondoms?\M|intimate gel|\mlubricant\M|contraceptive)' then
                case when i.store_slug in ('communitypharma') then '06' else '12' end
            -- 6. Clothing services traps
            when i.canonical_name ~* 'dry cleaning' then '03'
            when i.canonical_name ~* 'laundry' and i.canonical_name ~* '(service|wash)' then '03'
            when i.canonical_name ~* '\mtailor\M' or i.canonical_name ~* 'tailor alteration' then '03'
            -- 7. Personal care services & grooming tools traps -> 12
            when i.canonical_name ~* '(nail scissor|nail scissors|cuticle scissor|cuticle scissors|manicure scissor|manicure scissors|nail clipper|nail clippers|nail file|nail files|cuticle nipper|cuticle pusher|manicure set|pedicure set|emery board|nail buffer|nail buffers|nail file buffer|buffer blue|foeycai|nail shiner|nail care)' then '12'
            when i.canonical_name ~* 'haircut' or i.canonical_name ~* 'hair salon' then '12'
            when i.canonical_name ~* 'beauty salon' or i.canonical_name ~* 'nail salon' then '12'
            when i.canonical_name ~* '\mspa\M' or i.canonical_name ~* '\mmassage\M' then '12'
            when i.canonical_name ~* 'visa fee' or i.canonical_name ~* '\mpassport\M' then '12'
            when i.canonical_name ~* 'travel insurance' or (i.canonical_name ~* 'insurance' and i.canonical_name ~* '(travel|health|medical)') then '12'
            -- 8. Recreation & culture services traps -> 09
            when i.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'new_gasoline', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') and (
                i.canonical_name ~* 'gym membership' or i.canonical_name ~* '\mgym\M' or i.canonical_name ~* '\mfitness\M'
                or i.canonical_name ~* 'yoga class' or i.canonical_name ~* 'swimming pool'
                or i.canonical_name ~* '\mkaraoke\M' or i.canonical_name ~* '\mbowling\M'
                or i.canonical_name ~* '\mcinema\M' or i.canonical_name ~* 'cinema ticket' or i.canonical_name ~* 'movie theater' or i.canonical_name ~* '\mtheatre\M'
                or i.canonical_name ~* 'museum entry' or i.canonical_name ~* '\mmuseum\M' or i.canonical_name ~* '\mgallery\M' or i.canonical_name ~* 'exhibition'
                or i.canonical_name ~* 'concert' or i.canonical_name ~* 'theme park' or i.canonical_name ~* 'water park' or i.canonical_name ~* 'amusement park' or i.canonical_name ~* '\mzoo\M'
                or (i.canonical_name ~* '\mtour\M' and i.canonical_name ~* '(guide|ticket|package|1day)')
                or i.canonical_name ~* 'travel agent'
            ) then '09'
            -- 9. Pets & pet food traps -> 09 (UN COICOP 09.3.4)
            when i.category_native ~* '^(Pets|Pet\s*Care|Pet\s*Food)' then '09'
            when i.canonical_name ~* '(dog food|cat food|pet food|dog treat|cat treat|dog snack|cat snack|puppy food|kitten food|cat litter|dog toy|cat toy|pet toy|pet accessory|pet accessories|pet shampoo|royal canin|pedigree|whiskas|friskies|purina|me-o|smartheart|sheba|felix|cesar|drools|jerhigh|pro plan|cattitude|ganador|maxime dog|maxime cat|dog patÃ©|cat patÃ©|dog pate|cat pate)' then '09'
            -- 10. Specific Food traps
            when (i.canonical_name ~* 'bamboo shoot' or i.canonical_name ~* 'lotus root' or i.canonical_name ~* 'kaffir lime' or (i.canonical_name ~* 'lemongrass' and i.canonical_name !~* '(spray|fragrance|diffus|oil|aroma|candle)') or i.canonical_name ~* 'galangal') then '01'
            when i.canonical_name ~* 'fish sauce' or i.canonical_name ~* 'oyster sauce' or i.canonical_name ~* 'soy sauce' or i.canonical_name ~* 'sriracha' or i.canonical_name ~* 'curry paste' or i.canonical_name ~* 'palm sugar' then '01'
            when i.canonical_name ~* 'coconut milk' or i.canonical_name ~* 'coconut cream' or i.canonical_name ~* 'rice noodle' or i.canonical_name ~* 'glass noodle' or i.canonical_name ~* 'instant noodle' or i.canonical_name ~* 'instant coffee' then '01'
            when i.canonical_name ~* 'soy milk' or i.canonical_name ~* 'tofu' or i.canonical_name ~* 'tempeh' or i.canonical_name ~* 'edamame' or i.canonical_name ~* 'coconut water' then '01'
            when i.canonical_name ~* 'condensed milk' or i.canonical_name ~* 'evaporated milk' or i.canonical_name ~* 'powdered milk' or i.canonical_name ~* 'baby formula' or i.canonical_name ~* 'infant formula' then '01'
            when i.canonical_name ~* '\mham\M' or i.canonical_name ~* '\mbacon\M' or i.canonical_name ~* '\msausage\M' or i.canonical_name ~* 'salami' or i.canonical_name ~* '\mpepperoni\M' or i.canonical_name ~* 'jerky' then '01'
            when i.canonical_name ~* 'cooking oil' or i.canonical_name ~* 'vegetable oil' or i.canonical_name ~* 'olive oil' or i.canonical_name ~* 'sesame oil' then '01'
            when i.canonical_name ~* 'coconut oil' and i.canonical_name ~* '(cook|fry|food|kitchen|edible)' and i.canonical_name !~* '(hair|skin|body|shampoo)' then '01'
            when i.canonical_name ~* '(mixed nuts|salted nuts|roasted nuts|cashew nuts|peanuts|almonds|walnuts|pistachios|\mnuts?\M)' then '01'
            -- 13. Real estate & residential rental properties -> 04 Housing (UN COICOP 04.1.1)
            when i.canonical_name ~* '(apartment for rent|condo for rent|villa for rent|house for rent|room for rent|studio for rent|residential rent|property for rent|penthouse for rent|shophouse for rent|serviced apartment|borey peng huoth|borey chankiri|\mborey\M|urban village phase|riverfront condo|wooden villa|link villa|prime location.*property)' then '04'
            -- 14. Bus & passenger transport tickets -> 07 (BookMeBus, RedBus)
            when i.canonical_name ~* '(bus ticket|express bus|vip van|ferry ticket|bus fare|sleeper bus|giant ibis|larita|virak buntham|mey hong)' then '07'
            -- 15. Medical & surgical gloves, baby diaper pants
            when i.canonical_name ~* '(surgical gloves|latex gloves|sterile gloves|examination gloves|medical gloves|wound dressing|callus dressing)' then
                case when i.store_slug in ('aeon', 'aeon3') then '12' else '06' end
            when i.canonical_name ~* '(baby pants|pull up pants|diaper pants|\mdiapers?\M)' then '12'
            -- 16. Food & confectionery false-match clothing traps -> 01 Food
            when i.canonical_name ~* '(salad dressing|greek dressing|thousand island|caesar dressing|nuggets|chicken breast nuggets|chocolate nuggets|sugar coated|coated peas|corn flakes|bran flakes|cottonseed oil|teriyaki marinade|bratwurst)' then '01'
            -- 17. Toy dolls & toy tracks -> 09 Recreation
            when i.canonical_name ~* '(hot wheels|track set|track builder|barbie|teresa doll|\mdolls?\M|action figure|board game)' then '09'
            -- 18. Art, stationery, and drawing materials -> 09 Recreation
            when i.canonical_name ~* '(charcoal sticks|drawing charcoal|sketching charcoal|sketch pad|sketch book|acrylic paint|oil paint|watercolor|watercolour|paint brush|stationery)' then '09'
            else null
        end as trap_division
    from items i
),
store_purity as (
    -- Single-division stores: whatever these sources list, it belongs to one
    -- COICOP division by construction (pharmacies sell health, real-estate
    -- portals list housing, etc.). Keyword/AI/trap signals must never break
    -- this invariant (see tests: test_communitypharma_coicop_06,
    -- test_realestate_khmer24_coicop_04, test_coicop_08_stores_only,
    -- test_coicop_11_stores_only, test_no_tech_or_housing_in_coicop_12).
    select
        i.item_id,
        i.store_slug,
        case
            when i.store_slug in ('communitypharma') then '06'
            when i.store_slug in ('khmer24', 'realestate') then '04'
            when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11'
            when i.store_slug in ('bookmebus', 'redbus', 'redmebus', 'new_gasoline') then '07'
            when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'
        end as purity_division
    from items i
)
select
    i.item_id,
    i.store_slug,
    i.canonical_name,
    i.category_native,
    i.product_key,
    i.price_khr,
    coalesce(
        ov_exact.coicop_division,
        ps.purity_division,
        case
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then
                case
                    when ai.coicop_division = '04' and i.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                    when ai.coicop_division = '07' and i.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
                    else ai.coicop_division
                end
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) < 0.50 then 'REVIEW'
        end,
        ov_global.coicop_division,
        t.trap_division,
        kw_strong.kw_division,
        cm.coicop_division,
        kw_weak.kw_division,
        case when i.store_slug in ('khmer24', 'realestate') then '04' end,
        case when i.store_slug in ('communitypharma') then '06' end,
        case when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11' end,
        case when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07' end,
        case when i.store_slug in ('new_gasoline') then '07' end,
        case when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08' end,
        sd.coicop_division,
        'UNCLASSIFIED'
    ) as coicop_division,
    coalesce(
        case when ov_exact.coicop_division is not null then ov_exact.coicop_division end,
        case
            when ps.purity_division is not null then
                case ps.purity_division
                    when '06' then '06.1.2'
                    when '04' then '04.1.1'
                    when '11' then '11.2.0'
                    when '07' then case when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' else '07.2.2' end
                    when '08' then '08.2.0'
                end
        end,
        case
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then
                case
                    when ai.coicop_division = '04' and i.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                    when ai.coicop_division = '07' and i.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
                    else ai.coicop_code
                end
        end,
        case when ov_global.coicop_division is not null then ov_global.coicop_division end,
        t.trap_division,
        kw_strong.kw_division,
        cm.coicop_division,
        kw_weak.kw_division,
        case when i.store_slug in ('khmer24', 'realestate') then '04.1.1' end,
        case when i.store_slug in ('communitypharma') then '06.1.2' end,
        case when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11.2.0' end,
        case when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' end,
        case when i.store_slug in ('new_gasoline') then '07.2.2' end,
        case when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08.2.0' end,
        sd.coicop_division,
        'UNCLASSIFIED'
    ) as coicop_code,
    case
        when ov_exact.coicop_division is not null then 'override'
        when ps.purity_division is not null then 'store_default'
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50
             and not (ai.coicop_division = '04' and i.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus'))
             and not (ai.coicop_division = '07' and i.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
             then 'gemini_ai'
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) < 0.50 then 'gemini_ai_low_conf'
        when ov_global.coicop_division is not null then 'override'
        when t.trap_division is not null then 'exception'
        when kw_strong.kw_division is not null then 'keyword_ladder'
        when cm.coicop_division is not null then 'category_map'
        when kw_weak.kw_division is not null then 'keyword_ladder'
        when i.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 'store_default'
        when sd.coicop_division is not null then 'store_default'
        else 'unclassified'
    end as coicop_method,
    case
        when ov_exact.coicop_division is not null then 1.000
        when ps.purity_division is not null then 0.850
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then coalesce(ai.confidence_score, 0.900)
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) < 0.50 then 0.400
        when ov_global.coicop_division is not null then 1.000
        when t.trap_division is not null then 0.990
        when kw_strong.kw_division is not null then 0.950
        when cm.coicop_division is not null then 0.900
        when kw_weak.kw_division is not null then 0.950
        when i.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 0.850
        when sd.coicop_division is not null then coalesce(sd.confidence_score, 0.800)
        else 0.000
    end as coicop_confidence
from items i
left join trap_divisions t
    on t.item_id = i.item_id and t.store_slug = i.store_slug
left join store_purity ps
    on ps.item_id = i.item_id and ps.store_slug = i.store_slug
left join lateral (
    -- Tier 1: authoritative human rules â€” exact identifiers (barcode /
    -- product_key, any store tag) or name rules explicitly tagged to THIS
    -- store. These beat store purity by design.
    select lpad(ov.coicop_division, 2, '0') as coicop_division
    from (
        select match_type, match_value, store_slug, coicop_division
        from {{ ref('coicop_override') }}
        union all
        select match_type, match_value, store_slug, coicop_division
        from {{ source('silver', 'coicop_override_manual') }}
    ) ov
    where (ov.store_slug is null or ov.store_slug = '' or ov.store_slug = i.store_slug)
      and (
            (ov.match_type = 'barcode' and i.barcode is not null and trim(i.barcode) = trim(ov.match_value))
            or (ov.match_type = 'product_key' and trim(i.product_key) = trim(ov.match_value))
            or (ov.match_type = 'name'
                and ov.store_slug = i.store_slug
                and position(lower(trim(ov.match_value)) in lower(trim(i.canonical_name))) > 0)
      )
    limit 1
) ov_exact on true
left join lateral (
    -- Tier 2b: global (store-agnostic) name-substring rules. Ranked BELOW ai
    -- so that a broad keyword rule cannot override a precise AI result or
    -- violate a pure store's invariant.
    select lpad(ov.coicop_division, 2, '0') as coicop_division
    from (
        select match_type, match_value, store_slug, coicop_division
        from {{ ref('coicop_override') }}
        union all
        select match_type, match_value, store_slug, coicop_division
        from {{ source('silver', 'coicop_override_manual') }}
    ) ov
    where ov.match_type = 'name'
      and (ov.store_slug is null or ov.store_slug = '')
      and position(lower(trim(ov.match_value)) in lower(trim(i.canonical_name))) > 0
    limit 1
) ov_global on true
left join lateral (
    select
        gated.coicop_code,
        case
            when split_part(gated.coicop_code, '.', 1) in ('12', '13') then '12'
            else lpad(split_part(gated.coicop_code, '.', 1), 2, '0')
        end as coicop_division,
        gated.confidence_score
    from (
        select
            case
                -- Store-context gates mirror the purity tests: an AI answer of
                -- 08 outside telecom stores or 11 outside hotels is invalid
                -- and must fall through to lower tiers.
                when split_part(ai.coicop_code, '.', 1) = '08'
                     and i.store_slug not in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then null::text
                when split_part(ai.coicop_code, '.', 1) = '11'
                     and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null::text
                else ai.coicop_code
            end as coicop_code,
            ai.confidence_score
        from {{ source('silver', 'dim_coicop_ai_cache') }} ai
        where lower(regexp_replace(trim(ai.product_name), '\s+', ' ', 'g')) = lower(regexp_replace(trim(i.canonical_name), '\s+', ' ', 'g'))
          and ai.coicop_code <> '99.9.9'
        limit 1
    ) gated
) ai on true
left join lateral (
    -- STRONG keyword rules (priority < 300): high-precision division blocks
    -- (clothing, cosmetics, alcohol, household...). Ranked ABOVE category_map
    -- because scrapers often collapse unrelated shelves into generic native
    -- categories (e.g. AEON tags fashion items as 'Grocery').
    select lpad(k.division::text, 2, '0') as kw_division
    from {{ ref('coicop_keywords') }} k
    where k.priority::int < 300
      and case when coalesce(k.match_column, 'canonical_name') = 'category_native'
               then coalesce(i.category_native, '')
               else i.canonical_name end
          ~* nullif(trim(k.match_regex), '')
      and (
            nullif(trim(k.and_regex), '') is null
            or (case when coalesce(k.match_column, 'canonical_name') = 'category_native'
                     then coalesce(i.category_native, '')
                     else i.canonical_name end ~* trim(k.and_regex))
          )
      and (
            nullif(trim(k.negate_regex), '') is null
            or (case when coalesce(k.match_column, 'canonical_name') = 'category_native'
                     then coalesce(i.category_native, '')
                     else i.canonical_name end !~* trim(k.negate_regex))
          )
      and (
            coalesce(k.exclude_stores, '') = ''
            or not (i.store_slug = any(string_to_array(replace(k.exclude_stores, ' ', ''), ',')))
          )
      and (
            coalesce(k.include_stores, '') = ''
            or i.store_slug = any(string_to_array(replace(k.include_stores, ' ', ''), ','))
          )
    order by k.priority asc
    limit 1
) kw_strong on true
left join lateral (
    select lpad(cm.coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }} cm
    where cm.store_slug = i.store_slug
      and lower(trim(cm.category_native)) = lower(trim(i.category_native))
    limit 1
) cm on true
left join lateral (
    -- WEAK keyword rules (priority >= 300): broad food vocabulary.
    -- Ranked BELOW category_map; only fires when the store taxonomy misses.
    select lpad(k.division::text, 2, '0') as kw_division
    from {{ ref('coicop_keywords') }} k
    where k.priority::int >= 300
      and case when coalesce(k.match_column, 'canonical_name') = 'category_native'
               then coalesce(i.category_native, '')
               else i.canonical_name end
          ~* nullif(trim(k.match_regex), '')
      and (
            nullif(trim(k.and_regex), '') is null
            or (case when coalesce(k.match_column, 'canonical_name') = 'category_native'
                     then coalesce(i.category_native, '')
                     else i.canonical_name end ~* trim(k.and_regex))
          )
      and (
            nullif(trim(k.negate_regex), '') is null
            or (case when coalesce(k.match_column, 'canonical_name') = 'category_native'
                     then coalesce(i.category_native, '')
                     else i.canonical_name end !~* trim(k.negate_regex))
          )
      and (
            coalesce(k.exclude_stores, '') = ''
            or not (i.store_slug = any(string_to_array(replace(k.exclude_stores, ' ', ''), ',')))
          )
      and (
            coalesce(k.include_stores, '') = ''
            or i.store_slug = any(string_to_array(replace(k.include_stores, ' ', ''), ','))
          )
    order by k.priority asc
    limit 1
) kw_weak on true
left join lateral (
    select
        lpad(sd.default_coicop_division, 2, '0') as coicop_division,
        sd.confidence as confidence_score
    from {{ ref('coicop_store_defaults') }} sd
    where sd.store_slug = i.store_slug
      and sd.is_active = true
    limit 1
) sd on true
