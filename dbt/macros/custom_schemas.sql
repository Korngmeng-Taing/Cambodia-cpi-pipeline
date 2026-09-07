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


{#
    clean_product_name — single-source-of-truth mirror of
    `pipeline/text_clean.py:clean_name_for_matching()`.

    C2 fix: requires explicit currency anchor before matching digits, so
    package sizes (e.g. "330ml", "500g") survive into the cleaned name.
    Package size for unit-price math comes from `raw_payload.package_size`.

    Order of operations matches the Python pipeline:
      1. HTML entity decode
      2. Khmer numerals → ASCII digits
      3. Price strip (anchored: $ or ៛ prefix OR explicit USD/KHR/RIEL/៛/$ suffix)
      4. Promo-word strip
      5. Khmer compound translation (longest-first to avoid 'ទឹកដោះគោ' → 'WATER BEEF')
      6. Collapse whitespace, upper-case
#}
{% macro clean_product_name(raw_name) %}
    upper(
        regexp_replace(
            -- 5. Khmer terms in strict longest-first order (H9 fix: 'ទឹកដោះគោ' -> 'MILK' before 'ទឹក' / 'គោ')
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
            regexp_replace(
                -- 4. Promo words
                regexp_replace(
                    -- 3. Prices (currency-anchored; sizes preserved)
                    regexp_replace(
                        -- 2. Khmer numerals → ASCII
                        translate(
                            -- 1. HTML entity decode
                            replace(
                            replace(
                            replace(
                            replace(
                            replace(
                            replace(
                            replace(
                            replace(
                            replace(
                                coalesce({{ raw_name }}, ''),
                                '&#8211;', '-'
                            ),
                            '&#8212;', '-'
                            ),
                            '&#8243;', '"'
                            ),
                            '&#038;', '&'
                            ),
                            '&amp;', '&'
                            ),
                            '&quot;', '"'
                            ),
                            '&#39;', ''''
                            ),
                            '&apos;', ''''
                            ),
                            '&nbsp;', ' '
                            ),
                            '០១២៣៤៥៦៧៨៩',
                            '0123456789'
                        ),
                        '[$៛]\s*\d{1,3}(?:[,.\\s]\d{3})*(?:[.,]\d{1,2})?|\d{1,3}(?:[,.\\s]\d{3})*(?:[.,]\d{1,2})?\s*(?:KHR|USD|RIEL|៛|\$)|(?:KHR|USD|RIEL)\s+\d{1,3}(?:[,.\\s]\d{3})*(?:[.,]\d{1,2})?',
                        ' ',
                        'g'
                    ),
                    '\y(SALE|PROMO|PROMOTION|DISCOUNT|CLEARANCE|HOT\s*DEAL|BEST\s*SELLER|NEW\s*ARRIVAL|LIMITED|SPECIAL\s*OFFER|FLASH\s*SALE|BUY\s*\d+\s*GET\s*\d+|FREE\s*SHIPPING|BUNDLE)\y',
                    ' ',
                    'gi'
                ),
                'អង្ករផ្កាម្លិះ', ' JASMINE RICE ', 'g'),
                'ប្រេងម៉ាស៊ូត', ' DIESEL ', 'g'),
                'ទឹកបរិសុទ្ធ', ' WATER ', 'g'),
                'ទឹកដោះគោ', ' MILK ', 'g'),
                'ប្រេងសាំង', ' GASOLINE ', 'g'),
                'សាច់មាន់', ' CHICKEN ', 'g'),
                'សាច់ជ្រូក', ' PORK ', 'g'),
                'ស្រាបៀរ', ' BEER ', 'g'),
                'ប្រេងឆា', ' COOKING OIL ', 'g'),
                'ម៉ាស៊ូត', ' DIESEL ', 'g'),
                'ពងមាន់', ' CHICKEN EGG ', 'g'),
                'ផ្លែឈើ', ' FRUIT ', 'g'),
                'កាហ្វេ', ' COFFEE ', 'g'),
                'នំប៉័ង', ' BREAD ', 'g'),
                'សាច់គោ', ' BEEF ', 'g'),
                'ពងទា', ' DUCK EGG ', 'g'),
                'ស្ករស', ' SUGAR ', 'g'),
                'អំបិល', ' SALT ', 'g'),
                'បន្លែ', ' VEGETABLE ', 'g'),
                'សាំង', ' GASOLINE ', 'g'),
                'អង្ករ', ' RICE ', 'g'),
                'ស៊ុត', ' EGG ', 'g'),
                'ទឹក', ' WATER ', 'g'),
                'គោ', ' BEEF ', 'g'),
            '\s+', ' ', 'g'
        )
    )
{% endmacro %}
