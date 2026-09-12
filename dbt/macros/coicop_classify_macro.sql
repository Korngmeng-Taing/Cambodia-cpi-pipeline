{% macro resolve_coicop_division(
    cache_div,
    ov_exact_div, purity_division, trap_div,
    ai_div, ai_conf,
    ov_global_div,
    cat_map_div, text_rule_div,
    store_default_div, store_slug) %}
    coalesce(
        {{ cache_div }},
        {{ ov_exact_div }},
        {{ purity_division }},
        {{ trap_div }},
        {{ ai_div }},
        {{ ov_global_div }},
        {{ text_rule_div }},
        {{ cat_map_div }},
        {{ store_default_div }},
        'UNCLASSIFIED'
    )
{% endmacro %}

{% macro resolve_coicop_code(
    cache_code,
    ai_div, ai_code, ai_conf,
    purity_division, purity_code,
    trap_div, trap_code,
    ov_exact_div, ov_global_div,
    cat_map_div, cat_map_code,
    text_rule_div, text_rule_code,
    store_default_div, store_default_code, store_slug) %}
    coalesce(
        {{ cache_code }},
        case when {{ ov_exact_div }} is not null then {{ coicop_code_from_division(ov_exact_div) }} end,
        {{ purity_code }},
        {{ trap_code }},
        case
            when {{ ai_div }} is not null then
                case
                    when {{ ai_code }} ~ '^\d{2}(\.\d{1,2}){1,3}$' then {{ ai_code }}
                    else {{ coicop_code_from_division(ai_div) }}
                end
        end,
        case when {{ ov_global_div }} is not null then {{ coicop_code_from_division(ov_global_div) }} end,
        case
            when {{ text_rule_code }} is not null then {{ text_rule_code }}
            when {{ text_rule_div }} is not null then {{ coicop_code_from_division(text_rule_div) }}
        end,
        case
            when {{ cat_map_code }} is not null then {{ cat_map_code }}
            when {{ cat_map_div }} = '09' then '09.5.1'
            when {{ cat_map_div }} is not null then {{ coicop_code_from_division(cat_map_div) }}
        end,
        case when {{ store_default_code }} is not null then {{ store_default_code }}
             when {{ store_default_div }} is not null then {{ coicop_code_from_division(store_default_div) }}
        end,
        'UNCLASSIFIED'
    )
{% endmacro %}

{% macro resolve_coicop_method(
    cache_div,
    ov_exact_div, purity_division, trap_div, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, text_rule_div, store_slug, store_default_div) %}
    case
        when {{ cache_div }} is not null then 'cache'
        when {{ ov_exact_div }} is not null then 'override'
        when {{ purity_division }} is not null then 'store_purity'
        when {{ trap_div }} is not null then 'critical_trap'
        when {{ ai_div }} is not null then 'gemini_ai'
        when {{ ov_global_div }} is not null then 'override'
        when {{ text_rule_div }} is not null then 'text_rules'
        when {{ cat_map_div }} is not null then 'category_map'
        when {{ store_default_div }} is not null then 'store_default'
        else 'unclassified'
    end
{% endmacro %}

{% macro resolve_coicop_confidence(
    cache_conf,
    ov_exact_div, purity_division, trap_div, ov_global_div,
    ai_div, ai_conf,
    cat_map_div, text_rule_div, text_rule_conf,
    store_slug, store_default_div, store_default_conf) %}
    coalesce(
        {{ cache_conf }},
        case when {{ ov_exact_div }} is not null then 1.000 end,
        case when {{ purity_division }} is not null then 0.850 end,
        case when {{ trap_div }} is not null then 0.950 end,
        case when {{ ai_div }} is not null then coalesce({{ ai_conf }}, 0.900) end,
        case when {{ ov_global_div }} is not null then 1.000 end,
        case when {{ text_rule_div }} is not null then coalesce({{ text_rule_conf }}, 0.950) end,
        case when {{ cat_map_div }} is not null then 0.900 end,
        case when {{ store_default_div }} is not null then coalesce({{ store_default_conf }}, 0.800) end,
        0.000
    )
{% endmacro %}

