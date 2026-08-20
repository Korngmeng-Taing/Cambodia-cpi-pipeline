-- int_coicop_classified
-- COICOP division classification ladder (see COICOP_MAPPING.md and AUDIT_REPORT.md).
-- One row per (item_id, store_slug) from int_prices_cleaned.
--
-- Resolution order (first match wins):
--   1. override       -> coicop_override seed (name / barcode / product_key match)
--   2. gemini_ai      -> silver.dim_coicop_ai_cache (cached classifications with normalized key)
--   3. exceptions     -> deterministic trap regex (COOKING WINE -> 01, medical masks -> 06, etc.)
--   4. keyword ladder -> ordered regex per division (order: 12, 02, 05, 03, 06, 09,
--                        07, 08, 11, 10, 04, 01)
--   5. category_map   -> silver.coicop_category_map (store native category -> division)
--   6. store_default  -> coicop_store_defaults seed
--   7. UNCLASSIFIED / REVIEW -> fallback for triage & Gemini AI
{{ config(
    materialized='view'
) }}

with items as (
    select
        p.item_id::text as item_id,
        p.store_slug,
        min(p.name_clean) as canonical_name,
        min(p.barcode) as barcode,
        min(p.category_native) as category_native,
        p.item_id::text as product_key,
        round(exp(avg(ln(p.price_khr)) filter (where p.price_khr > 0)), 2) as price_khr
    from {{ ref('int_prices_cleaned') }} p
    where p.item_id is not null
    group by p.item_id, p.store_slug
),
trap_divisions as (
    select
        i.item_id,
        i.store_slug,
        case
            -- 1. Medical / protective masks -> 06 Health (MUST precede cosmetics)
            when i.canonical_name ~* '(protecting mask|protective mask|surgical mask|medical mask|earloop|ear loop|earlooped|kn95|n95|ffp2|ffp3|melt[- ]?blown)' then '06'
            -- 2. Industrial / tool safety masks -> 05 Furnishings & maintenance
            when i.canonical_name ~* '(gas mask|dust mask|respirator mask)' then '05'
            -- 3. School / office tape -> 10 Education
            when i.canonical_name ~* 'masking tape' then '10'
            -- 4. High-priority deterministic exception traps
            when i.canonical_name ~* 'cooking wine' then '01'
            when i.canonical_name ~* 'somersby cider' then '02'
            when i.canonical_name ~* 'wolf blass' then '02'
            when i.canonical_name ~* 'tvhc slipper' then '03'
            when i.canonical_name ~* 'lix floor cleaner' then '05'
            when i.canonical_name ~* 'tv coffee filter' then '05'
            when i.canonical_name ~* 'green onion slicer' then '05'
            when i.canonical_name ~* 'little trees' then '05'
            when i.canonical_name ~* 'my-ring notes' then '09'
            when i.canonical_name ~* 'wakame mixed rice with salmon' then '01'
            when i.canonical_name ~* 'spicy beef hot pot' then '01'
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
                case when i.store_slug in ('communitypharma', 'pharmacy', 'u-care', 'ucare') then '06' else '12' end
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
            when i.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'pharmacy', 'u-care', 'ucare', 'new_gasoline', 'tela', 'ptt', 'caltex', 'total', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') and (
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
            when i.canonical_name ~* '(dog food|cat food|pet food|dog treat|cat treat|dog snack|cat snack|puppy food|kitten food|cat litter|dog toy|cat toy|pet toy|pet accessory|pet accessories|pet shampoo|royal canin|pedigree|whiskas|friskies|purina|me-o|smartheart|sheba|felix|cesar|drools|jerhigh|pro plan|cattitude|ganador|maxime dog|maxime cat|dog paté|cat paté|dog pate|cat pate)' then '09'
            -- 10. Specific Food traps
            when i.canonical_name ~* 'bamboo shoot' or i.canonical_name ~* 'lotus root' or i.canonical_name ~* 'kaffir lime' or i.canonical_name ~* 'lemongrass' or i.canonical_name ~* 'galangal' then '01'
            when i.canonical_name ~* 'fish sauce' or i.canonical_name ~* 'oyster sauce' or i.canonical_name ~* 'soy sauce' or i.canonical_name ~* 'sriracha' or i.canonical_name ~* 'curry paste' or i.canonical_name ~* 'palm sugar' then '01'
            when i.canonical_name ~* 'coconut milk' or i.canonical_name ~* 'coconut cream' or i.canonical_name ~* 'rice noodle' or i.canonical_name ~* 'glass noodle' or i.canonical_name ~* 'instant noodle' or i.canonical_name ~* 'instant coffee' then '01'
            when i.canonical_name ~* 'soy milk' or i.canonical_name ~* 'tofu' or i.canonical_name ~* 'tempeh' or i.canonical_name ~* 'edamame' or i.canonical_name ~* 'coconut water' then '01'
            when i.canonical_name ~* 'condensed milk' or i.canonical_name ~* 'evaporated milk' or i.canonical_name ~* 'powdered milk' or i.canonical_name ~* 'baby formula' or i.canonical_name ~* 'infant formula' then '01'
            when i.canonical_name ~* '\mham\M' or i.canonical_name ~* '\mbacon\M' or i.canonical_name ~* '\msausage\M' or i.canonical_name ~* 'salami' or i.canonical_name ~* '\mpepperoni\M' or i.canonical_name ~* 'jerky' then '01'
            when i.canonical_name ~* 'cooking oil' or i.canonical_name ~* 'vegetable oil' or i.canonical_name ~* 'olive oil' or i.canonical_name ~* 'sesame oil' then '01'
            when i.canonical_name ~* 'coconut oil' and i.canonical_name ~* '(cook|fry|food|kitchen|edible)' and i.canonical_name !~* '(hair|skin|body|shampoo)' then '01'
            when i.canonical_name ~* '(mixed nuts|salted nuts|roasted nuts|cashew nuts|peanuts|almonds|walnuts|pistachios|\mnuts?\M)' then '01'
            when i.canonical_name ~* 'tv salted mixed nuts' then '01'
            -- 12. Tech gadgets, phones & telecom traps -> 08 (Strictly for arystore, samnangshop, cellcard, smart)
            when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'
            -- 13. Real estate & residential rental properties -> 04 Housing (UN COICOP 04.1.1)
            when i.store_slug in ('khmer24', 'realestate') then '04'
            when i.canonical_name ~* '(apartment for rent|condo for rent|villa for rent|house for rent|room for rent|studio for rent|residential rent|property for rent|penthouse for rent|shophouse for rent|serviced apartment|borey peng huoth|borey chankiri|\mborey\M|urban village phase|riverfront condo|wooden villa|link villa|prime location.*property)' then '04'
            -- 14. Bus & passenger transport tickets -> 07 (BookMeBus, RedBus)
            when i.store_slug in ('bookmebus', 'redbus') then '07'
            when i.canonical_name ~* '(bus ticket|express bus|vip van|ferry ticket|bus fare|sleeper bus|giant ibis|larita|virak buntham|mey hong)' then '07'
            -- 15. Medical & surgical gloves, baby diaper pants
            when i.canonical_name ~* '(surgical gloves|latex gloves|sterile gloves|examination gloves|medical gloves|wound dressing|callus dressing)' then
                case when i.store_slug in ('aeon', 'aeon3') then '12' else '06' end
            when i.canonical_name ~* '(baby pants|pull up pants|diaper pants|\mdiapers?\M)' then '12'
            -- 16. Food & confectionery false-match clothing traps -> 01 Food
            when i.canonical_name ~* '(salad dressing|greek dressing|thousand island|caesar dressing|nuggets|chicken breast nuggets|chocolate nuggets|sugar coated|coated peas|corn flakes|bran flakes|cottonseed oil|teriyaki marinade|bratwurst)' then '01'
            -- 17. Toy dolls & toy tracks -> 09 Recreation
            when i.canonical_name ~* '(hot wheels|track set|track builder|barbie|teresa doll|\mdolls?\M|action figure|board game)' then '09'
            else null
        end as trap_division
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
        case when i.store_slug in ('khmer24', 'realestate') then '04' end,
        case when i.store_slug in ('communitypharma', 'pharmacy', 'u-care', 'ucare') then '06' end,
        case when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11' end,
        case when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07' end,
        case when i.store_slug in ('new_gasoline', 'tela', 'ptt', 'caltex', 'total') then '07' end,
        case when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08' end,
        case
            when ov.coicop_division = '08' and i.store_slug not in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then null
            when ov.coicop_division = '06' and i.store_slug in ('aeon', 'aeon3', 'delishop') then '12'
            when ov.coicop_division = '07' and i.store_slug in ('aeon', 'aeon3', 'delishop', 'l192') then '05'
            when ov.coicop_division = '11' and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '01'
            else ov.coicop_division
        end,
        case
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then ai.coicop_division
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) < 0.50 then 'REVIEW'
        end,
        case
            when t.trap_division = '08' and i.store_slug not in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then null
            when t.trap_division = '06' and i.store_slug in ('aeon', 'aeon3', 'delishop') then '12'
            when t.trap_division = '07' and i.store_slug in ('aeon', 'aeon3', 'delishop', 'l192') then '05'
            when t.trap_division = '11' and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '01'
            else t.trap_division
        end,
        kw.kw_division,
        cm.coicop_division,
        sd.coicop_division,
        'UNCLASSIFIED'
    ) as coicop_division,
    coalesce(
        ai.coicop_code,
        ov.coicop_division,
        t.trap_division,
        kw.kw_division,
        cm.coicop_division,
        sd.coicop_division,
        'UNCLASSIFIED'
    ) as coicop_code,
    case
        when i.store_slug in ('khmer24', 'realestate') then 'store_default'
        when i.store_slug in ('communitypharma', 'pharmacy', 'u-care', 'ucare') then 'store_default'
        when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then 'store_default'
        when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then 'store_default'
        when i.store_slug in ('new_gasoline', 'tela', 'ptt', 'caltex', 'total') then 'store_default'
        when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 'store_default'
        when ov.coicop_division is not null then 'override'
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then 'gemini_ai'
        when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) < 0.50 then 'gemini_ai_low_conf'
        when t.trap_division is not null then 'exception'
        when kw.kw_division is not null then 'keyword_ladder'
        when cm.coicop_division is not null then 'category_map'
        when sd.coicop_division is not null then 'store_default'
        else 'unclassified'
    end as coicop_method,
    case
        when i.store_slug in ('khmer24', 'realestate') then 1.000
        when i.store_slug in ('communitypharma', 'pharmacy', 'u-care', 'ucare') then 1.000
        when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then 1.000
        when i.store_slug in ('bookmebus', 'redbus', 'redmebus') then 1.000
        when i.store_slug in ('new_gasoline', 'tela', 'ptt', 'caltex', 'total') then 1.000
        when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 1.000
        when ov.coicop_division is not null then 1.000
        when ai.coicop_division is not null then coalesce(ai.confidence_score, 0.900)
        when t.trap_division is not null then 0.990
        when kw.kw_division is not null then 0.950
        when cm.coicop_division is not null then 0.900
        when sd.coicop_division is not null then coalesce(sd.confidence_score, 0.800)
        else 0.000
    end as coicop_confidence
from items i
left join trap_divisions t
    on t.item_id = i.item_id and t.store_slug = i.store_slug
left join lateral (
    select lpad(ov.coicop_division, 2, '0') as coicop_division
    from {{ ref('coicop_override') }} ov
    where (ov.store_slug is null or ov.store_slug = '' or ov.store_slug = i.store_slug)
      and (
            (ov.match_type = 'name'
                and position(lower(trim(ov.match_value)) in lower(trim(i.canonical_name))) > 0)
            or (ov.match_type = 'barcode' and i.barcode is not null and trim(i.barcode) = trim(ov.match_value))
            or (ov.match_type = 'product_key' and trim(i.product_key) = trim(ov.match_value))
      )
    limit 1
) ov on true
left join lateral (
    select
        ai.coicop_code,
        lpad(split_part(ai.coicop_code, '.', 1), 2, '0') as coicop_division,
        ai.confidence_score
    from {{ source('silver', 'dim_coicop_ai_cache') }} ai
    where lower(regexp_replace(trim(ai.product_name), '\s+', ' ', 'g')) = lower(regexp_replace(trim(i.canonical_name), '\s+', ' ', 'g'))
      and ai.coicop_code <> '99.9.9'
    limit 1
) ai on true
left join lateral (
    select lpad(cm.coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }} cm
    where cm.store_slug = i.store_slug
      and lower(trim(cm.category_native)) = lower(trim(i.category_native))
    limit 1
) cm on true
left join lateral (
    select
        case
            -- 12 Miscellaneous (personal care, beauty, skincare, baby care, jewelry, watches, personal effects)
            when (
                i.canonical_name ~* '(cosmetic|cosmetics|makeup|lipstick|mascara|eyeliner|eyeshadow|foundation|concealer|blush|perfume|cologne|eau de|body mist|fragrance|shampoo|conditioner|body wash|shower gel|shower cream|shower foam|bath foam|bubble bath|shower oil|bath oil|body lotion|face lotion|lotion|deodorant|antiperspirant|sunblock|sunscreen|sun care|spf|toothpaste|toothbrush|dental floss|mouthwash|razor|shaving|shaver|soap|handsoap|hand soap|facial cleanser|face wash|moisturizer|moisturiser|lip balm|lip gloss|nail polish|nail polish remover|cotton bud|cotton pad|cotton wool|cotton swab|hair oil|hair cream|hair gel|hair spray|hair mousse|beard oil|aftershave|nail scissor|nail scissors|cuticle scissor|cuticle scissors|manicure scissor|manicure scissors|nail clipper|nail clippers|nail file|nail files|nail buffer|nail buffers|nail file buffer|foeycai|cuticle nipper|cuticle pusher|manicure|pedicure|emery board|nail buffer|nail shiner|nail care|tweezers|comb|brush|hairbrush|hair comb|face mask|sheet mask|eye cream|hand cream|body cream|hand lotion|facial serum|toner|cleanser|exfoliat|\mmask\M|mask sheet|mask pack|mask box|facial mask|facemask|eye mask|hair mask|foot mask|body mask|body scrub|face scrub|foot scrub|face cream|night cream|day cream|moisturizing cream|cleansing cream|tone up cream|foot cream|soothing gel|peeling gel|cica|collagen dream|vital perfection|future solution|ampoule|shiseido|nature republic|yadah|eunyul|bioderma|biolane|sanosan|dr medica|skin clinic|paxmoly|hair vitamin|hair clinic|baby lotion|baby oil|baby powder|baby wash|baby shampoo|baby bath|baby care|jewelry|jewellery|necklace|necklaces|earring|earrings|bracelet|bracelets|ring|rings|diamond|sunglass|sunglasses|wrist watch|quartz watch|analog watch|\mwatch(es)?\M|purse|purses|wallet|wallets|umbrella|umbrellas|lighter|lighters|haircut|hair salon|beauty salon|nail salon|spa|massage|visa fee|passport)'
                and i.store_slug not in ('khmer24', 'realestate', 'communitypharma', 'pharmacy', 'u-care', 'ucare', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'new_gasoline', 'tela', 'ptt', 'caltex', 'total', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'arystore', 'samnangshop')
                and i.canonical_name !~* '(apple watch|galaxy watch|huawei watch|smart watch|smartwatch|watch fit|watch gt|galaxy fit|gas mask|dust mask|masking tape|respirator|surgical mask|medical mask|protective mask|earloop)'
            ) then '12'

            -- 02 Alcohol and tobacco
            when (
                i.canonical_name ~* '(beer|wine|vodka|whiskey|whisky|\mrum\M|\mgin\M|\msake\M|cider|liquor|tobacco|cigarette|spirit|shiraz|soju|champagne|brandy|tequila|mezcal|absinthe|bitters|port wine|tawny port|ruby port|vintage port|sherry|merlot|cabernet|chardonnay|pinot|riesling|lager|stout|pilsner|pale ale|craft ale|ginger ale|ipa ale|\male beer\M|brown ale|amber ale|\mlao\M|angkor beer|cambodia beer|king dommer|gabriel|tribeca|coors|heineken|budweiser|corona|carlsberg|san miguel|\mleo\M|\mchang beer\M|\mchang\M|singha|saigon|me Kong|phnom penh beer|cigar|nicotine|vape|e-cigarette|hookah|shisha|rolling paper|blunt wrap|snus|\mbong\M)'
                and i.canonical_name !~* '(changvar|chroy changvar|chroy changva|chang va|usb|charger|charging|cable|adapter|hub|socket|hdmi|type-c|lightning|power strip|power bank|audio|amplifier|headphone|earphone|connector|female to male|male to female)'
            ) then '02'

            -- 05 Furnishings, household equipment & maintenance
            -- cup noodles/soups/yogurts are FOOD (01), not crockery (05)
            when i.canonical_name ~* '\mcup\M' and i.canonical_name ~* '(noodle|noodles|soup|yogurt|yoghurt|fruit|pudding|jelly|dessert|salad|coffee|tea|drink|shake)' then '01'
            when (
                i.canonical_name ~* '(detergent|bleach|dish soap|dishwashing|cleaning|cleaner|cleaning spray|surface cleaner|broom|mop|bucket|towel|towels|linen|pillow|pillows|blanket|blankets|curtain|curtains|cookware|kettle|blender|toaster|vacuum|vacuum cleaner|\miron\M|ironing|sofa|couch|chair|chairs|\mtables?\M|bed|bedframe|headboard|lamp|lamps|utensil|utensils|cutlery|glassware|plate|plates|bowl|bowls|cup|cups|mug|mugs|sponge|sponges|trash|garbage|furniture|\mpan\M|pans|pots?|wok|frying pan|saucepan|stockpot|pressure cooker|rice cooker|air fryer|oven|microwave|electric fan|ceiling fan|standing fan|air conditioner|refrigerator|fridge|freezer|washing machine|dryer|dishwasher|water heater|gas stove|induction cooker|coffee maker|coffee machine|espresso|grill|barbecue|bbq|patio furniture|garden hose|lawn mower|tool kit|drill|screwdriver|hammer|wrench|pliers|saw|paint|glue|tape measure|toilet paper|paper towel|tissue|trash bag|laundry basket|clothes hanger|shelf|shelves|wardrobe|dresser|desk|office chair|gas mask|dust mask)'
                and i.store_slug not in ('khmer24', 'realestate', 'bookmebus', 'redbus', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'pharmacy', 'u-care', 'ucare', 'new_gasoline', 'tela', 'ptt', 'caltex', 'total', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi')
            ) then '05'

            -- 03 Clothing and footwear
            when (
                i.canonical_name ~* '(t-shirt|tshirt|\mshirt(s)?\M|\mdress(es)?\M|jeans|\mtrousers?\M|\msocks?\M|shoes|sneakers?|boots?|sandals?|\mslippers?\M|jacket|\mcoats?\M|underwear|\mbras?\M|panties|boxer|hoodie|sweater|blouse|skirt|scarf|\mgloves?\M|\mcaps?\M|\mhats?\M|\mties?\M|\mshorts?\M|\mpants?\M|leggings|cardigan|\mvests?\M|uniform|polo shirt|romper|jumpsuit|kimono|sarong|denim pants|flip flop|crocs|\m(high )?heels\M|loafers?|dry cleaning|tailor alteration)'
                and i.store_slug not in ('khmer24', 'realestate', 'bookmebus', 'redbus', 'communitypharma', 'arystore', 'samnangshop')
                and i.canonical_name !~* '(salad dressing|wound dressing|dressing|dressings|coated|coating|base coat|top coat|hot wheels|braided|bravia|brand|bracelet|baby pants|pull up pants|training pants|diaper|nappy|surgical gloves|latex gloves|medical gloves|rubber gloves|cleaning gloves|dishwashing gloves|wool detergent|woolite|laundry detergent|laundry liquid|laundry powder|cotton bud|cotton pad|cotton disk|cotton ball|cotton wool|cotton swab|cottonseed|oil|shower gel|case|cover|holder|strap|power strip|socket|spark|cable|speaker|soundbar|airtag|luggage|doll|barbie|hot pot|chocolate|nuggets|salt|sugar|syrup|flakes|chips|snack)'
            ) then '03'

            -- 06 Health (pharmaceuticals, medicines, medical consumables)
            when (
                i.canonical_name ~* '(medicine|medication|paracetamol|ibuprofen|panadol|bandage|bandages|first aid|thermometer|antibiotic|aspirin|cough syrup|cough medicine|inhaler|pharmacy|pharmaceutical|prescription|ointment|eyedrops|ear drops|lozenge|throat spray|nasal spray|antihistamine|pain reliever|pain relief|muscle rub|liniment|antiseptic|disinfectant|alcohol swab|gauze|medical tape|glucometer|blood pressure|insulin|hospital|clinic|doctor|medical|dental|eye test|eye exam|contact lens|lens solution|surgical mask|medical mask|kn95|n95|ffp2|ffp3|melt-blown|whey protein|protein powder|fish oil|omega 3|probiotic|melatonin|glucosamine)'
                and i.store_slug not in ('aeon', 'aeon3', 'khmer24', 'realestate', 'bookmebus', 'redbus', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk')
                and i.canonical_name !~* '(ice cream|sour cream|cream puff|creamy|cream stew|fruit drops|jelly|gel blaster|shampoo|shower gel|soothing gel|peeling gel|face cream|eye cream|night cream|day cream|moisturizing cream|tone up cream|foot cream|hair clinic|collagen dream|shiseido|cica|yadah|eunyul|moringa|biolane|sanosan|nature republic|paxmoly|stella gel|ambi pur|air freshener|tank top|tubetop|camisole|withcup)'
            ) then '06'

            -- 09 Recreation and culture (including Pets & related products)
            when i.category_native ~* '^(Pets|Pet\s*Care|Pet\s*Food)'
                 and i.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'redmebus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '09'
            when (
                i.canonical_name ~* '(dog food|cat food|pet food|dog treat|cat treat|dog snack|cat snack|puppy food|kitten food|puppy|kitten|cat litter|pet toy|dog toy|cat toy|pet accessory|pet accessories|pet toileteries|pet shampoo|dog shampoo|cat shampoo|pet crate|dog paté|cat paté|dog pate|cat pate|pedigree|whiskas|royal canin|purina|friskies|me-o|smartheart|sheba|felix|cesar|drools|pro plan|hills science|jerhigh|cattitude|ganador|maxime|bird seed|fish food|aquarium|\mtoy(s)?\M|doll|dolls|puzzle|puzzles|game|games|chess|badminton|football|soccer|basketball|tennis|stationery|camera|cameras|headphone|headphones|earphone|earphones|earbuds|speaker|speakers|console|playstation|xbox|nintendo|switch|bicycle|bicycles|guitar|guitars|piano|keyboards|keyboard|bookshelf speaker|soundbar|projector|tripod|selfie stick|drone|gopro|memory card|sd card|hard drive|ssd|usb drive|flash drive|power bank|smart home|lego|board game|gym|fitness|yoga class|swimming pool|karaoke|bowling|cinema|movie theater|theatre|concert|theme park|water park|amusement park|zoo|museum|gallery|exhibition|tour|travel agent)'
                and i.store_slug not in ('khmer24', 'realestate', 'l192', 'bookmebus', 'redbus', 'redmebus', 'samnangshop', 'arystore', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'communitypharma', 'pharmacy', 'u-care', 'ucare', 'new_gasoline', 'tela', 'ptt', 'caltex', 'total', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi')
            ) then '09'

            -- 07 Transport
            when (
                i.canonical_name ~* '(gasoline|petrol|diesel|fuel|engine oil|motor oil|lubricant|oil filter|air filter|tire|tyre|tires|tyres|motorbike|motorcycle|helmet|helmets|vehicle|airline|air ticket|bus ticket|bus fare|taxi|grab|passenger|scooter|car wash|car care|car accessory|parking|toll|ferry|auto parts|brake|brakes|clutch|spark plug|car battery|windshield|wiper|headlight|seat cover|steering wheel|shock absorber|wheel|wheels|rim|rims)'
                and i.store_slug not in ('khmer24', 'realestate', 'communitypharma', 'pharmacy', 'u-care', 'ucare', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore')
                and i.canonical_name !~* '(car charger|car phone holder|car mount|car adapter|hot wheels|track set)'
            ) then '07'

            -- 08 Communication
            -- Strictly restricted to electronics phone shops and telecom operators
            when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'

            -- 11 Restaurants and hotels
            -- Strictly restricted to hotels and restaurant sources
            when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11'

            -- 10 Education (school supplies ONLY)
            when i.canonical_name ~* '(exercise book|copy book|textbook|school book|school bag|notebook|notebooks|crayon|crayons|eraser|erasers|sharpener|pencil sharpener|pencil case|pencilcase|ball pen|ballpoint pen|gel pen|hb pencil|pencils|colour pencil|color pencil|ruler|rulers|protractor|geometry set|colouring book|drawing book|sketchbook|watercolour|paint set|scissors|glue stick|correction tape|highlighter|highlighters|marker|markers|whiteboard|chalk|calculator|graph paper|loose leaf|flashcards|binder|masking tape)' then '10'

            -- 04 Housing, water, electricity, gas & other fuels
            -- Strictly for real estate portals (khmer24, realestate) and utility tariffs
            when i.store_slug in ('khmer24', 'realestate') then '04'
            when (
                i.store_slug in ('utility_tariffs', 'l192')
                and i.canonical_name ~* '(\melectricity\M|\melectric bill\M|\mpower bill\M|\mwater bill\M|\mwater rate\M|\mwater tariff\M|\mlpg cylinder\M|\mgas cylinder\M|\mgas tank\M|\mresidential rental\M)'
            ) then '04'

            -- 01 Food and non-alcoholic beverages
            when (
                i.canonical_name ~* '(rice|noodle|noodles|pasta|spaghetti|bread|loaf|bun|buns|roll|rolls|croissant|baguette|cereal|oats|oatmeal|flour|sugar|palm sugar|salt|pepper|chili|cumin|turmeric|ginger|garlic|onion|shallot|lemongrass|galangal|kaffir lime|cinnamon|vanilla|cocoa|chocolate|candy|jelly|jam|honey|maple syrup|syrup|sauce|ketchup|mayonnaise|mustard|vinegar|soy sauce|fish sauce|oyster sauce|sriracha|curry paste|tomato paste|meat|chicken|pork|beef|\msausage\M|\mbacon\M|\mham\M|salami|\mpepperoni\M|jerky|canned tuna|canned sardine|canned bean|canned soup|pickled|kimchi|dried fruit|raisin|coconut milk|coconut cream|coconut water|tofu|tempeh|soy milk|beans|lentils|peas|morning glory|water spinach|cabbage|carrot|cucumber|tomato|eggplant|potato|sweet potato|lettuce|spinach|broccoli|cauliflower|corn|mushroom|\mapples?\M|banana|mango|orange|grape|watermelon|papaya|pineapple|avocado|milk|cheese|butter|yogurt|egg|eggs|cooking oil|olive oil|vegetable oil|coconut oil|sesame oil|sunflower oil|canola oil|peanut oil|soybean oil|\mnuts?\M|mixed nuts|salted nuts|roasted nuts|peanuts?|cashews?|almonds?|walnuts?|pistachios?|hazelnuts?|macadamias?|chestnuts?|sunflower seeds?|pumpkin seeds?|snacks?|chips|crisps|crackers?|biscuits?|cookies?|wafers?|popcorn)'
                and i.canonical_name !~* '(iphone|ipad|macbook|apple watch|apple pencil|airpods|homepod|usb-c|lightning|charger|adapter|cable|case|silicone|leather case|pro max|ultra|\d+gb)'
            ) then '01'

            else null
        end as kw_division
) kw on true
left join lateral (
    select
        lpad(sd.default_coicop_division, 2, '0') as coicop_division,
        sd.confidence as confidence_score
    from {{ ref('coicop_store_defaults') }} sd
    where sd.store_slug = i.store_slug
      and sd.is_active = true
    limit 1
) sd on true
