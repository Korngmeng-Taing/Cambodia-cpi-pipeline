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
        when {{ div_expr }} ~ '^\d{2}(\.\d{1,2}){1,3}$' then {{ div_expr }}
        when {{ div_expr }} ~ '^\d{2}\.unclassified$' then {{ div_expr }}
        when {{ div_expr }} ~ '^\d{2}$' then {{ div_expr }} || '.unclassified'
        when {{ div_expr }} ~ '^\d{1}$' then '0' || {{ div_expr }} || '.unclassified'
        else 'UNCLASSIFIED'
    end
{% endmacro %}
