{#
    Custom schema resolution — materializes every model/seed directly into the
    schema declared in dbt_project.yml (bronze / staging / silver / gold),
    ignoring the target schema prefix.

    e.g. models/silver/fct_daily_prices.sql with `+schema: silver` → silver.fct_daily_prices
#}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
