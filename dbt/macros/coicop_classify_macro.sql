{% macro resolve_coicop_division(
    ov_exact_div, purity_division, trap_div,
    ai_div, ai_conf,
    ov_global_div,
    cat_map_div, text_rule_div,
    store_default_div, store_slug) %}
    coalesce(
        {{ ov_exact_div }},
        {{ purity_division }},
        {{ trap_div }},
        -- High-confidence Gemini AI (>= 0.70)
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.70 then {{ ai_div }}
        end,
        {{ ov_global_div }},
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.50 then {{ ai_div }}
        end,
        {{ text_rule_div }},
        {{ cat_map_div }},
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) <  0.50 then 'REVIEW'
        end,
        {{ store_default_div }},
        'UNCLASSIFIED'
    )
{% endmacro %}


{% macro resolve_coicop_code(
    ai_div, ai_code, ai_conf,
    purity_division, purity_code,
    trap_div, trap_code,
    ov_exact_div, ov_global_div,
    cat_map_div, cat_map_code,
    text_rule_div, text_rule_code,
    store_default_div, store_default_code, store_slug) %}
    coalesce(
        -- 1. Exact overrides
        case
            when {{ ov_exact_div }} is not null
                then {{ coicop_code_from_division(ov_exact_div) }}
        end,
        -- 2. Store purity locks
        {{ purity_code }},
        -- 3. Critical Traps
        {{ trap_code }},
        -- 4. Gemini AI high-confidence classification (>= 0.70)
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.70 then
                case
                    when {{ ai_code }} is not null
                         and {{ ai_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                         and lpad(split_part({{ ai_code }}, '.', 1), 2, '0') = {{ ai_div }}
                        then {{ ai_code }}
                    else {{ coicop_code_from_division(ai_div) }}
                end
        end,
        -- 5. Global name substring overrides
        case
            when {{ ov_global_div }} is not null
                then {{ coicop_code_from_division(ov_global_div) }}
        end,
        -- 6. Gemini AI medium-confidence classification (>= 0.50)
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.50 then
                case
                    when {{ ai_code }} is not null
                         and {{ ai_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                         and lpad(split_part({{ ai_code }}, '.', 1), 2, '0') = {{ ai_div }}
                        then {{ ai_code }}
                    else {{ coicop_code_from_division(ai_div) }}
                end
        end,
        -- 7. Text regex rules
        case
            when {{ text_rule_code }} is not null
                 and {{ text_rule_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                 and lpad(split_part({{ text_rule_code }}, '.', 1), 2, '0') = {{ text_rule_div }}
                then {{ text_rule_code }}
            when {{ text_rule_div }} is not null
                then {{ coicop_code_from_division(text_rule_div) }}
        end,
        -- 8. Category map
        case
            when {{ cat_map_code }} is not null
                 and {{ cat_map_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                 and lpad(split_part({{ cat_map_code }}, '.', 1), 2, '0') = {{ cat_map_div }}
                then {{ cat_map_code }}
            when {{ cat_map_div }} = '09' then '09.5.1'
            when {{ cat_map_div }} is not null
                then {{ coicop_code_from_division(cat_map_div) }}
        end,
        -- 8b. Low-confidence AI check
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) < 0.50 then 'REVIEW'
        end,
        -- 9. Store-level defaults & single-source fallbacks
        case when {{ store_slug }} in ('khmer24', 'realestate') then '04.1.1' end,
        case when {{ store_slug }} = 'edc' then '04.5.1' end,
        case when {{ store_slug }} = 'ppwsa' then '04.4.1' end,
        case when {{ store_slug }} in ('communitypharma', 'grab_ucare') then '06.1.2' end,
        case when {{ store_slug }} in ('sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt') then '11.2.0' end,
        case when {{ store_slug }} in ('bayonbkk') then '11.1.1' end,
        case when {{ store_slug }} in ('bookmebus', 'redbus', 'redmebus') then '07.3.2' end,
        case when {{ store_slug }} in ('new_gasoline') then '07.2.2' end,
        case when {{ store_slug }} = 'khmermoto' then '07.1.2' end,
        case when {{ store_slug }} in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone') then '08.3.0' end,
        case when {{ store_slug }} in ('arystore', 'samnangshop') then '08.2.0' end,
        case when {{ store_slug }} in ('delishop', 'aeon', 'grab_lucky', 'grab_chipmong') then '01.unclassified' end,
        case when {{ store_slug }} in ('aeon3') then '03.unclassified' end,
        case when {{ store_slug }} in ('l192') then '05.unclassified' end,
        case
            when {{ store_default_code }} is not null
                 and {{ store_default_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then {{ store_default_code }}
            when {{ store_default_div }} is not null
                 then {{ coicop_code_from_division(store_default_div) }}
        end,
        'UNCLASSIFIED'
    )
{% endmacro %}


{% macro resolve_coicop_method(
    ov_exact_div, purity_division, trap_div, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, text_rule_div, store_slug, store_default_div) %}
    case
        when {{ ov_exact_div }} is not null then 'override'
        when {{ purity_division }} is not null then 'store_purity'
        when {{ trap_div }} is not null then 'critical_trap'
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.70 then 'gemini_ai'
        when {{ ov_global_div }} is not null then 'override'
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.50 then 'gemini_ai'
        when {{ text_rule_div }} is not null then 'text_rules'
        when {{ cat_map_div }} is not null then 'category_map'
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) <  0.50 then 'review'
        when {{ store_slug }} in (
            'khmer24', 'realestate', 'sokhahotel',
            'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk',
            'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
            'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone',
            'khmermoto', 'edc', 'ppwsa', 'arystore', 'samnangshop'
        ) then 'store_purity'
        when {{ store_default_div }} is not null then 'store_default'
        else 'unclassified'
    end
{% endmacro %}


{% macro resolve_coicop_confidence(
    ov_exact_div, purity_division, trap_div, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, text_rule_div, text_rule_conf,
    store_slug, store_default_div, store_default_conf) %}
    case
        when {{ ov_exact_div }} is not null then 1.000
        when {{ purity_division }} is not null then 0.850
        when {{ trap_div }} is not null then 0.950
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.70 then coalesce({{ ai_conf }}, 0.900)
        when {{ ov_global_div }} is not null then 1.000
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.50 then coalesce({{ ai_conf }}, 0.900)
        when {{ text_rule_div }} is not null then coalesce({{ text_rule_conf }}, 0.950)
        when {{ cat_map_div }} is not null then 0.900
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) <  0.50 then 0.400
        when {{ store_slug }} in (
            'khmer24', 'realestate', 'sokhahotel',
            'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk',
            'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
            'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone',
            'khmermoto', 'edc', 'ppwsa', 'arystore', 'samnangshop'
        ) then 0.850
        when {{ store_default_div }} is not null then coalesce({{ store_default_conf }}, 0.800)
        else 0.000
    end
{% endmacro %}

