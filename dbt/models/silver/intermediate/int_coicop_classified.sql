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
    select distinct on (p.item_id, p.store_slug)
        p.item_id::text as item_id,
        p.store_slug,
        ci.canonical_name,
        ci.barcode,
        p.category_native,
        p.item_id::text as product_key,
        null::numeric as price_khr,
        lower(regexp_replace(trim(ci.canonical_name), '\s+', ' ', 'g')) as norm_name,
        lower(trim(coalesce(p.category_native, ''))) as norm_category
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
    where not exists (
        select 1 from {{ this }} t
        where t.item_id = p.item_id::text
          and t.store_slug = p.store_slug
          and t.coicop_method = 'override'
    )
    {% endif %}
),
all_overrides as (
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ ref('coicop_override') }}
    union all
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_override_manual') }}
),
ov_barcode as (
    select distinct on (match_value)
        match_value as barcode,
        coicop_division
    from all_overrides
    where match_type = 'barcode' and match_value is not null and match_value <> ''
),
ov_product_key as (
    select distinct on (match_value)
        match_value as product_key,
        coicop_division
    from all_overrides
    where match_type = 'product_key' and match_value is not null and match_value <> ''
),
ov_name_store as (
    select distinct on (store_slug, match_val_lower)
        match_val_lower, store_slug, coicop_division
    from all_overrides
    where match_type = 'name' and store_slug is not null and store_slug <> ''
),
store_purity as (
    select
        i.item_id,
        i.store_slug,
        case
            when i.store_slug in ('khmer24', 'realestate') then '04'
            when i.store_slug in ('communitypharma') then '06'
            when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11'
            when i.store_slug in ('bookmebus', 'redbus', 'redmebus', 'new_gasoline') then '07'
            when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'
        end as purity_division
    from items i
),
ai_prejoined as (
    select distinct on (lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')))
        lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')) as norm_name,
        coicop_code,
        case
            when split_part(coicop_code, '.', 1) in ('12', '13') then '12'
            else lpad(split_part(coicop_code, '.', 1), 2, '0')
        end as coicop_division,
        confidence_score
    from {{ source('silver', 'dim_coicop_ai_cache') }}
    where coicop_code <> '99.9.9'
),
cat_map_prejoined as (
    select distinct on (store_slug, lower(trim(category_native)))
        store_slug,
        lower(trim(category_native)) as cat_key,
        lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }}
),
store_defaults_prejoined as (
    select distinct on (store_slug)
        store_slug,
        lpad(default_coicop_division, 2, '0') as coicop_division,
        confidence as confidence_score
    from {{ ref('coicop_store_defaults') }}
    where is_active = true
),
items_fast as (
    select
        i.item_id,
        i.store_slug,
        i.canonical_name,
        i.barcode,
        i.product_key,
        i.price_khr,
        i.norm_name,
        i.category_native,
        i.norm_category,
        coalesce(ov_b.coicop_division, ov_pk.coicop_division) as ov_exact_id_div,
        ps.purity_division,
        case
            when split_part(ai.coicop_code, '.', 1) = '08' and i.store_slug not in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then null
            when split_part(ai.coicop_code, '.', 1) = '11' and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
            else ai.coicop_division
        end as ai_div,
        ai.confidence_score as ai_conf,
        ai.coicop_code as ai_code,
        cm.coicop_division as cat_map_div,
        sd.coicop_division as store_default_div,
        sd.confidence_score as store_default_conf
    from items i
    left join store_purity ps on ps.item_id = i.item_id and ps.store_slug = i.store_slug
    left join ai_prejoined ai on ai.norm_name = i.norm_name
    left join ov_barcode ov_b on i.barcode is not null and trim(i.barcode) <> '' and ov_b.barcode = trim(i.barcode)
    left join ov_product_key ov_pk on i.product_key is not null and trim(i.product_key) <> '' and ov_pk.product_key = trim(i.product_key)
    left join cat_map_prejoined cm on cm.store_slug = i.store_slug and cm.cat_key = i.norm_category
    left join store_defaults_prejoined sd on sd.store_slug = i.store_slug
),
unresolved_items as (
    select f.item_id, f.store_slug, f.canonical_name, f.norm_category
    from items_fast f
    where f.ov_exact_id_div is null
      and f.purity_division is null
      and f.ai_div is null
),
ov_name_store_matched as (
    select distinct on (u.item_id, u.store_slug)
        u.item_id,
        u.store_slug,
        o.coicop_division
    from unresolved_items u
    join ov_name_store o
      on o.store_slug = u.store_slug
     and position(o.match_val_lower in lower(u.canonical_name)) > 0
),
traps_and_keywords as (
    select
        u.item_id,
        u.store_slug,
        -- Traps
        case
            when u.canonical_name ~* '(shampoo|conditioner|hair mask|body wash|shower gel|shower cream|shower foam|bubble bath|facial cleanser|face wash|bar soap|hand soap|toothpaste|mouthwash)' then null
            when u.canonical_name ~* '(protecting mask|protective mask|surgical mask|medical mask|earloop|ear loop|earlooped|kn95|n95|ffp2|ffp3|melt[- ]?blown)' then
                case when u.store_slug in ('aeon', 'aeon3') then '12' else '06' end
            when u.canonical_name ~* '(gas mask|dust mask|respirator mask)' then '05'
            when u.canonical_name ~* 'masking tape' then '10'
            when u.canonical_name ~* 'cooking wine' then '01'
            when u.canonical_name ~* '\m(somersby cider|somersby|wolf blass|martell|ballantine|ballantine`s|chivas|johnnie walker|hoegaarden|sapporo|shochu|remy martin|hennessy|glenfiddich|macallan|jack daniel|jim beam|smirnoff|absolut|bacardi|captain morgan|tanqueray|bombay sapphire|jagermeister|baileys|kahlua|aperol|campari|bottega|limoncino|mouton cadet|anchor ultra|kirishima)\M'
                 and u.canonical_name !~* '(sauce|marinade|bourguignon|braised|vinegar)' then '02'
            when u.canonical_name ~* '\m(rohto|tiger balm|kwan loong|naga balm|bow balm|eye drops?|eyedrops|medicated plaster|cooling plaster)\M' then '06'
            when u.canonical_name ~* '\m(bio-oil|bio oil|hadalabo|cetaphil|saforelle|klorane|old spice|hair serum|facial serum|ambient spray|air freshener)\M'
                 and u.canonical_name !~* '(cookie|biscuit|candy|snack|tea|drink)' then '12'
            when u.canonical_name ~* 'tvhc slipper' then '03'
            when u.canonical_name ~* 'lix floor cleaner' then '05'
            when u.canonical_name ~* 'tv coffee filter' then '05'
            when u.canonical_name ~* 'green onion slicer' then '05'
            when u.canonical_name ~* 'little trees' then '05'
            when u.canonical_name ~* 'my-ring notes' then '09'
            when u.canonical_name ~* 'wakame mixed rice with salmon' then '01'
            when u.canonical_name ~* 'spicy beef hot pot' then '01'
            when u.canonical_name ~* '(beef sparerib|spareribs?|bolognese spaghetti|campagna spaghetti|spaghetti|pasta|butter cookies|candy necklace|pringles)' then '01'
            when u.canonical_name ~* 'sunplay skin aqua' then '12'
            when u.canonical_name ~* 'lipice' then '12'
            when u.canonical_name ~* '\mhospital\M' then '06'
            when u.canonical_name ~* '\mclinic\M'
                 and u.canonical_name !~* '(shampoo|treatment|cream|serum|tonic|toothpaste|hair|skin|face|beauty|cosmetic|makeup|dental|oil|soap)' then '06'
            when u.canonical_name ~* '\mdoctor\M'
                 and u.canonical_name !~* '(playmobil|toy|set|bag|car|drink|energy|tote|mini|gift|costume)' then '06'
            when u.canonical_name ~* 'medical' and u.canonical_name ~* '(visit|consultation|checkup|examination|fee)' then '06'
            when u.canonical_name ~* 'dental' and u.canonical_name ~* '(visit|cleaning|filling|extraction|whitening)' then '06'
            when u.canonical_name ~* 'eye test' or u.canonical_name ~* 'eye exam' then '06'
            when u.canonical_name ~* 'contact lens' or u.canonical_name ~* 'lens solution' then '06'
            when u.canonical_name ~* '(ritex|durex|sagami|okamoto|\mcondoms?\M|intimate gel|\mlubricant\M|contraceptive)' then
                case when u.store_slug in ('communitypharma') then '06' else '12' end
            when u.canonical_name ~* 'dry cleaning' then '03'
            when u.canonical_name ~* 'laundry' and u.canonical_name ~* '(service|wash)' then '03'
            when u.canonical_name ~* '\mtailor\M' or u.canonical_name ~* 'tailor alteration' then '03'
            when u.canonical_name ~* '(nail scissor|nail scissors|cuticle scissor|cuticle scissors|manicure scissor|manicure scissors|nail clipper|nail clippers|nail file|nail files|cuticle nipper|cuticle pusher|manicure set|pedicure set|emery board|nail buffer|nail buffers|nail file buffer|buffer blue|foeycai|nail shiner|nail care)' then '12'
            when u.canonical_name ~* 'haircut' or u.canonical_name ~* 'hair salon' then '12'
            when u.canonical_name ~* 'beauty salon' or u.canonical_name ~* 'nail salon' then '12'
            when u.canonical_name ~* '\mspa\M' or u.canonical_name ~* '\mmassage\M' then '12'
            when u.canonical_name ~* 'visa fee' or u.canonical_name ~* '\mpassport\M' then '12'
            when u.canonical_name ~* 'travel insurance' or (u.canonical_name ~* 'insurance' and u.canonical_name ~* '(travel|health|medical)') then '12'
            when u.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'new_gasoline', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') and (
                u.canonical_name ~* 'gym membership' or u.canonical_name ~* '\mgym\M' or u.canonical_name ~* '\mfitness\M'
                or u.canonical_name ~* 'yoga class' or u.canonical_name ~* 'swimming pool'
                or u.canonical_name ~* '\mkaraoke\M' or u.canonical_name ~* '\mbowling\M'
                or u.canonical_name ~* '\mcinema\M' or u.canonical_name ~* 'cinema ticket' or u.canonical_name ~* 'movie theater' or u.canonical_name ~* '\mtheatre\M'
                or u.canonical_name ~* 'museum ticket' or u.canonical_name ~* 'admission fee'
                or u.canonical_name ~* 'concert ticket' or u.canonical_name ~* 'theme park'
                or u.canonical_name ~* 'badminton court' or u.canonical_name ~* 'football pitch' or u.canonical_name ~* 'futsal'
            ) then '09'
            else null
        end as trap_div,
        -- Strong keywords
        case
            when (u.canonical_name ~* '(t-shirt|tshirt|\mshirt(s)?\M|\mdress(es)?\M|jeans|\mtrousers?\M|\msocks?\M|shoes|sneakers?|boots?|sandals?|\mslippers?\M|jacket|\mcoats?\M|underwear|\mbras?\M|panties|boxer|hoodie|sweater|blouse|skirt|scarf|\mgloves?\M|\mcaps?\M|\mhats?\M|\mties?\M|\mshorts?\M|\mpants?\M|leggings|cardigan|\mvests?\M|uniform|polo shirt|romper|jumpsuit|kimono|sarong|denim pants|flip flop|crocs|\m(high )?heels\M|loafers?|dry cleaning|tailor alteration)')
                 and (u.canonical_name !~* '(salad dressing|wound dressing|dressing|dressings|coated|coating|base coat|top coat|hot wheels|braided|bravia|brand|bracelet|baby pants|pull up pants|training pants|diaper|nappy|surgical gloves|latex gloves|medical gloves|rubber gloves|cleaning gloves|dishwashing gloves|wool detergent|woolite|laundry detergent|laundry liquid|laundry powder|cotton bud|cotton pad|cotton disk|cotton ball|cotton wool|cottonseed|oil|shower gel|case|cover|holder|strap|power strip|socket|spark|cable|speaker|soundbar|airtag|luggage|doll|barbie|hot pot|chocolate|nuggets|salt|sugar|syrup|flakes|chips|snack)')
                 and (u.store_slug not in ('khmer24', 'realestate', 'bookmebus', 'redbus', 'communitypharma', 'arystore', 'samnangshop'))
                 then '03'
            when (u.canonical_name ~* '(medicine|medication|paracetamol|ibuprofen|panadol|bandage|bandages|first aid|thermometer|antibiotic|aspirin|cough syrup|cough medicine|inhaler|pharmacy|pharmaceutical|prescription|ointment|eyedrops|eye drop|rohto|tiger balm|kwan loong|naga balm|lozenge|throat spray|nasal spray|antihistamine|pain reliever|pain relief|muscle rub|liniment|antiseptic|disinfectant|alcohol swab|gauze|medical tape|glucometer|blood pressure|insulin|hospital|clinic|doctor|medical|dental|eye test|eye exam|contact lens|lens solution|surgical mask|medical mask|kn95|n95|ffp2|ffp3|melt-blown|whey protein|protein powder|fish oil|omega 3|probiotic|melatonin|glucosamine)')
                 and (u.canonical_name !~* '(ice cream|sour cream|cream puff|creamy|cream stew|fruit drops|jelly|gel blaster|shampoo|shower gel|soothing gel|peeling gel|face cream|eye cream|night cream|day cream|moisturizing cream|tone up cream|foot cream|hair clinic|collagen dream|shiseido|cica|yadah|eunyul|moringa|biolane|sanosan|nature republic|paxmoly|stella gel|ambi pur|air freshener|tank top|tubetop|camisole|withcup)')
                 and (u.store_slug not in ('aeon', 'aeon3', 'khmer24', 'realestate', 'bookmebus', 'redbus', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
                 then '06'
            when (u.norm_category ~* '^(Pets|Pet\s*Care|Pet\s*Food)')
                 and (u.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'redmebus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
                 then '09'
            when (u.canonical_name ~* '(dog food|cat food|pet food|dog treat|cat treat|dog snack|cat snack|puppy food|kitten food|puppy|kitten|cat litter|pet toy|dog toy|cat toy|pet accessory|pet accessories|pet toileteries|pet shampoo|dog shampoo|cat shampoo|pet crate|dog pat.|cat pat.|dog pate|cat pate|pedigree|whiskas|royal canin|purina|friskies|me-o|smartheart|sheba|felix|cesar|drools|pro plan|hills science|jerhigh|cattitude|ganador|maxime|bird seed|fish food|aquarium|\mtoy(s)?\M|doll|dolls|puzzle|puzzles|game|games|chess|badminton|football|soccer|basketball|tennis|stationery|camera|cameras|headphone|headphones|earphone|earphones|earbuds|speaker|speakers|console|playstation|xbox|nintendo|switch|bicycle|bicycles|guitar|guitars|piano|keyboards|keyboard|bookshelf speaker|soundbar|projector|tripod|selfie stick|drone|gopro|memory card|sd card|hard drive|ssd|usb drive|flash drive|power bank|smart home|lego|board game|gym|fitness|yoga class|swimming pool|karaoke|bowling|cinema|movie theater|theatre|concert|theme park|water park|amusement park|zoo|museum|gallery|exhibition|tour|travel agent)')
                 and (u.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'redmebus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'new_gasoline', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi'))
                 then '09'
            when (u.canonical_name ~* '(gasoline|petrol|diesel|fuel|engine oil|motor oil|lubricant|oil filter|air filter|tire|tyre|tires|tyres|motorbike|motorcycle|helmet|helmets|vehicle|airline|air ticket|bus ticket|bus fare|taxi|grab|passenger|scooter|car wash|car care|car accessory|parking|toll|ferry|auto parts|brake|brakes|clutch|spark plug|car battery|windshield|wiper|headlight|seat cover|steering wheel|shock absorber|wheel|wheels|\mrim\M|\mrims\M)')
                 and (u.canonical_name !~* '(car charger|car phone holder|car mount|car adapter|hot wheels|track set|shrimp)')
                 and (u.store_slug not in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore'))
                 then '07'
            when (u.canonical_name ~* '(exercise book|copy book|textbook|school book|school bag|notebook|notebooks|crayon|crayons|eraser|erasers|sharpener|pencil sharpener|pencil case|pencilcase|ball pen|ballpoint pen|gel pen|hb pencil|pencils|colour pencil|color pencil|ruler|rulers|protractor|geometry set|colouring book|drawing book|sketchbook|watercolour|paint set|scissors|glue stick|correction tape|highlighter|highlighters|marker|markers|whiteboard|chalk|calculator|graph paper|loose leaf|flashcards|binder|masking tape)') then '10'
            else null
        end as kw_strong_div,
        -- Weak keywords
        case
            when u.canonical_name ~* '(\melectricity\M|\melectric bill\M|\mpower bill\M|\mwater bill\M|\mwater rate\M|\mwater tariff\M|\mlpg cylinder\M|\mgas cylinder\M|\mgas tank\M|\mresidential rental\M)'
                 and (u.store_slug in ('utility_tariffs', 'l192'))
                 then '04'
            when (u.canonical_name ~* '(rice|noodles?|pasta|spaghetti|bread|loaf|croissant|baguette|cereal|oats|oatmeal|flour|tortilla|ketchup|mayonnaise|mustard|vinegar|soy sauce|fish sauce|oyster sauce|sriracha|curry paste|tomato paste|honey|maple syrup|\msyrup\M|pickled|kimchi|wasabi|chili|cumin|turmeric|ginger|garlic|onion|shallot|lemongrass|galangal|kaffir lime|cinnamon|vanilla|cocoa|coconut milk|coconut cream|coconut water|chocolate|\mcandy\M|\mjelly\M|\mjam\M|dried fruit|raisin|\mnuts?\M|peanut|cashew|almond|walnut|pistachio|hazelnut|crackers?|biscuits?|cookies?|wafers?|popcorn|potato chips|corn chips|tortilla chips|crisps|\mchicken\M|\mpork\M|\mbeef\M|\mmeat\M|\msausage\M|\mbacon\M|\mham\M|salami|\mpepperoni\M|jerky|canned tuna|canned sardine|canned bean|canned soup|tofu|tempeh|soy milk|condensed milk|evaporated milk|powdered milk|cheese|butter|yogurt|yoghurt|\meggs?\M|beans|lentils|peas|morning glory|water spinach|cabbage|carrot|cucumber|tomato|eggplant|potato|sweet potato|lettuce|spinach|broccoli|cauliflower|\mcorn\M|mushroom|\mapples?\M|banana|mango|\morange\M|grape|watermelon|papaya|pineapple|avocado|cooking oil|vegetable oil|olive oil|sesame oil|sunflower oil|canola oil|peanut oil|soybean oil)')
                 and (u.canonical_name !~* '(iphone|ipad|macbook|apple watch|apple pencil|airpods|homepod|usb-c|lightning|charger|adapter|cable|case|silicone|leather case|pro max|ultra|\d+gb)')
                 then '01'
            else null
        end as kw_weak_div
    from unresolved_items u
)
select
    f.item_id,
    f.store_slug,
    f.canonical_name,
    f.category_native,
    f.product_key,
    f.price_khr,
    coalesce(
        f.ov_exact_id_div,
        ov_ns.coicop_division,
        f.purity_division,
        case
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then
                case
                    when f.ai_div = '04' and f.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                    when f.ai_div = '07' and f.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
                    else f.ai_div
                end
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 'REVIEW'
        end,
        tk.trap_div,
        tk.kw_strong_div,
        f.cat_map_div,
        tk.kw_weak_div,
        case when f.store_slug in ('khmer24', 'realestate') then '04' end,
        case when f.store_slug in ('communitypharma') then '06' end,
        case when f.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11' end,
        case when f.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07' end,
        case when f.store_slug in ('new_gasoline') then '07' end,
        case when f.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08' end,
        f.store_default_div,
        'UNCLASSIFIED'
    ) as coicop_division,
    coalesce(
        case when f.ov_exact_id_div is not null or ov_ns.coicop_division is not null then coalesce(f.ov_exact_id_div, ov_ns.coicop_division) end,
        case
            when f.purity_division is not null then
                case f.purity_division
                    when '06' then '06.1.2'
                    when '04' then '04.1.1'
                    when '11' then '11.2.0'
                    when '07' then case when f.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' else '07.2.2' end
                    when '08' then '08.2.0'
                end
        end,
        case
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then
                case
                    when f.ai_div = '04' and f.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                    when f.ai_div = '07' and f.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
                    else f.ai_code
                end
        end,
        tk.trap_div,
        tk.kw_strong_div,
        f.cat_map_div,
        tk.kw_weak_div,
        case when f.store_slug in ('khmer24', 'realestate') then '04.1.1' end,
        case when f.store_slug in ('communitypharma') then '06.1.2' end,
        case when f.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11.2.0' end,
        case when f.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' end,
        case when f.store_slug in ('new_gasoline') then '07.2.2' end,
        case when f.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08.2.0' end,
        f.store_default_div,
        'UNCLASSIFIED'
    ) as coicop_code,
    case
        when f.ov_exact_id_div is not null or ov_ns.coicop_division is not null then 'override'
        when f.purity_division is not null then 'store_default'
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50
             and not (f.ai_div = '04' and f.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus'))
             and not (f.ai_div = '07' and f.store_slug in ('aeon', 'aeon3', 'communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
             then 'gemini_ai'
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 'gemini_ai_low_conf'
        when tk.trap_div is not null then 'exception'
        when tk.kw_strong_div is not null then 'keyword_ladder'
        when f.cat_map_div is not null then 'category_map'
        when tk.kw_weak_div is not null then 'keyword_ladder'
        when f.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 'store_default'
        when f.store_default_div is not null then 'store_default'
        else 'unclassified'
    end as coicop_method,
    case
        when f.ov_exact_id_div is not null or ov_ns.coicop_division is not null then 1.000
        when f.purity_division is not null then 0.850
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then coalesce(f.ai_conf, 0.900)
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 0.400
        when tk.trap_div is not null then 0.990
        when tk.kw_strong_div is not null then 0.950
        when f.cat_map_div is not null then 0.900
        when tk.kw_weak_div is not null then 0.950
        when f.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 0.850
        when f.store_default_div is not null then coalesce(f.store_default_conf, 0.800)
        else 0.000
    end as coicop_confidence
from items_fast f
left join traps_and_keywords tk on tk.item_id = f.item_id and tk.store_slug = f.store_slug
left join ov_name_store_matched ov_ns on ov_ns.item_id = f.item_id and ov_ns.store_slug = f.store_slug
