{#
  coicop_classify_macro.sql
  ─────────────────────────
  P3 #124 — Resolves the 12-division COICOP ladder by reusing one set of CASE
  branches across the model. Three macros accept bare column expressions
  (e.g. `f.ai_div`) so they can be called directly in any model.

  Usage in int_coicop_classified.sql:

      {{ resolve_coicop_division(
            'f.ov_exact_div', 'f.purity_division', 'f.ov_global_div',
            'f.ai_div', 'f.ai_conf',
            'f.cat_map_div', 'f.store_default_div', 'f.store_slug') }}
#}


{% macro resolve_coicop_division(
    ov_exact_div, purity_division, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, store_default_div, store_slug) %}
    coalesce(
        {{ ov_exact_div }},
        {{ purity_division }},
        {{ ov_global_div }},
        case
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.50 then {{ ai_div }}
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) <  0.50 then 'REVIEW'
        end,
        {{ cat_map_div }},
        {{ store_default_div }},
        'UNCLASSIFIED'
    )
{% endmacro %}


{% macro resolve_coicop_code(
    ai_div, ai_code, ai_conf,
    purity_division, store_slug,
    ov_exact_div, ov_global_div,
    cat_map_div, cat_map_code,
    store_default_div, store_default_code) %}
    coalesce(
        case
            when {{ ai_code }} is not null
                 and {{ ai_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then {{ ai_code }}
            when {{ ai_div }} is not null
                 and coalesce({{ ai_conf }}, 0.90) >= 0.50
                then {{ coicop_code_from_division(ai_div) }}
        end,
        case
            when {{ purity_division }} is not null then
                case {{ purity_division }}
                    when '06' then '06.1.2'
                    when '04' then '04.1.1'
                    when '11' then case
                        when {{ store_slug }} = 'bayonbkk' then '11.1.1' else '11.2.0'
                    end
                    when '07' then case
                        when {{ store_slug }} in ('bookmebus', 'redbus', 'redmebus') then '07.3.1'
                        else '07.2.2'
                    end
                    when '08' then case
                        when {{ store_slug }} in ('arystore', 'samnangshop') then '08.2.0'
                        else '08.3.0'
                    end
                end
        end,
        case
            when {{ ov_exact_div }} is not null
                then {{ coicop_code_from_division(ov_exact_div) }}
        end,
        case
            when {{ ov_global_div }} is not null
                then {{ coicop_code_from_division(ov_global_div) }}
        end,
        -- cat_map: '09' maps to '09.5.4' (stationery), not the macro default '09.1.1'.
        case
            when {{ cat_map_code }} is not null
                 and {{ cat_map_code }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then {{ cat_map_code }}
            when {{ cat_map_div }} = '09' then '09.5.1'
            when {{ cat_map_div }} is not null then
                case {{ cat_map_div }}
                    when '01' then '01.1.1'
                    when '02' then '02.1.1'
                    when '03' then '03.1.2'
                    when '04' then '04.1.1'
                    when '05' then '05.1.1'
                    when '06' then '06.1.1'
                    when '07' then '07.2.2'
                    when '08' then '08.2.0'
                    when '10' then '10.1.0'
                    when '11' then '11.1.1'
                    when '12' then '12.1.1'
                    else '01.1.1'
                end
        end,
        -- Single-source stores: explicit per (store_slug -> 5-digit code).
        case when {{ store_slug }} in ('khmer24', 'realestate') then '04.1.1' end,
        case when {{ store_slug }} in ('communitypharma') then '06.1.2' end,
        case when {{ store_slug }} in ('sokhahotel', 'hyyathotel', 'hyatt') then '11.2.0' end,
        case when {{ store_slug }} in ('bayonbkk') then '11.1.1' end,
        case when {{ store_slug }} in ('bookmebus', 'redbus', 'redmebus') then '07.3.1' end,
        case when {{ store_slug }} in ('new_gasoline') then '07.2.2' end,
        case when {{ store_slug }} in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08.3.0' end,
        case when {{ store_slug }} in ('arystore', 'samnangshop') then '08.2.0' end,
        case when {{ store_slug }} in ('delishop', 'aeon') then '01.1.1' end,
        case when {{ store_slug }} in ('aeon3') then '03.1.2' end,
        case when {{ store_slug }} in ('l192') then '05.1.1' end,
        -- P3 #125: prefer the seed-provided 5-digit code when present.
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
    ov_exact_div, purity_division, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, store_slug, store_default_div) %}
    -- Resolution order mirrors resolve_coicop_division() exactly.
    -- M7 FIX: When AI confidence < 0.50, division macro returns 'REVIEW';
    -- method should match with 'review' (not 'gemini_ai_low_conf').
    case
        when {{ ov_exact_div }} is not null then 'override'
        when {{ purity_division }} is not null then 'store_purity'
        when {{ ov_global_div }} is not null then 'override'
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.50 then 'gemini_ai'
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) <  0.50 then 'review'
        when {{ cat_map_div }} is not null then 'category_map'
        when {{ store_slug }} in (
            'khmer24', 'realestate', 'communitypharma', 'sokhahotel',
            'hyyathotel', 'hyatt', 'bayonbkk',
            'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
            'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi'
        ) then 'store_purity'
        when {{ store_default_div }} is not null then 'store_default'
        else 'unclassified'
    end
{% endmacro %}


{% macro resolve_coicop_confidence(
    ov_exact_div, purity_division, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, store_slug, store_default_div, store_default_conf) %}
    case
        when {{ ov_exact_div }} is not null then 1.000
        when {{ purity_division }} is not null then 0.850
        when {{ ov_global_div }} is not null then 1.000
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) >= 0.50 then coalesce({{ ai_conf }}, 0.900)
        when {{ ai_div }} is not null
             and coalesce({{ ai_conf }}, 0.90) <  0.50 then 0.400
        when {{ cat_map_div }} is not null then 0.900
        when {{ store_slug }} in (
            'khmer24', 'realestate', 'communitypharma', 'sokhahotel',
            'hyyathotel', 'hyatt', 'bayonbkk',
            'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
            'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi'
        ) then 0.850
        when {{ store_default_div }} is not null then coalesce({{ store_default_conf }}, 0.800)
        else 0.000
    end
{% endmacro %}
