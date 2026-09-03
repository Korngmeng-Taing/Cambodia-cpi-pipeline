{#
  coicop_division_macro.sql
  ────────────────────────
  Reusable macro that maps a 2-digit COICOP division code to the
  default 5-digit COICOP code (XX.Y.Z).  Eliminates the repeated
  12-line CASE blocks in int_coicop_classified.sql.

  Usage:  {{ coicop_code_from_division('f.ai_div') }}
#}

{% macro coicop_code_from_division(div_expr) %}
    case
        when {{ div_expr }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then {{ div_expr }}
        when {{ div_expr }} = '01' then '01.1.1'
        when {{ div_expr }} = '02' then '02.1.1'
        when {{ div_expr }} = '03' then '03.1.2'
        when {{ div_expr }} = '04' then '04.1.1'
        when {{ div_expr }} = '05' then '05.1.1'
        when {{ div_expr }} = '06' then '06.1.1'
        when {{ div_expr }} = '07' then '07.2.2'
        when {{ div_expr }} = '08' then '08.2.0'
        when {{ div_expr }} = '09' then '09.1.1'
        when {{ div_expr }} = '10' then '10.1.0'
        when {{ div_expr }} = '11' then '11.1.1'
        when {{ div_expr }} = '12' then '12.1.1'
        else '01.1.1'
    end
{% endmacro %}
