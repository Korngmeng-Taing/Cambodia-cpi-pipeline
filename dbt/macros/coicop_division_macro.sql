{#
  coicop_division_macro.sql
  ────────────────────────
  Maps a 2-digit COICOP division code or class code to the
  canonical NIS Cambodia 4-digit class code (DD.G.C).

  Usage:  {{ coicop_code_from_division('f.ai_div') }}
#}

{% macro coicop_code_from_division(div_expr) %}
    case
        when {{ div_expr }} ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then {{ div_expr }}
        when {{ div_expr }} in ('01', '1') then '01.1.1'
        when {{ div_expr }} in ('02', '2') then '02.1.3'
        when {{ div_expr }} in ('03', '3') then '03.1.2'
        when {{ div_expr }} in ('04', '4') then '04.1.1'
        when {{ div_expr }} in ('05', '5') then '05.6.1'
        when {{ div_expr }} in ('06', '6') then '06.1.1'
        when {{ div_expr }} in ('07', '7') then '07.2.2'
        when {{ div_expr }} in ('08', '8') then '08.2.0'
        when {{ div_expr }} in ('09', '9') then '09.3.1'
        when {{ div_expr }} in ('10') then '10.1.0'
        when {{ div_expr }} in ('11') then '11.1.1'
        when {{ div_expr }} in ('12') then '12.1.3'
        when {{ div_expr }} ~ '^\d{2}(\.\d{1,2}){1,3}$' then {{ div_expr }}
        else 'UNCLASSIFIED'
    end
{% endmacro %}
