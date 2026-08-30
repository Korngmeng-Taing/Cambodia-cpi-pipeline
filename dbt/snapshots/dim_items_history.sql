{% snapshot dim_items_history %}

{{
    config(
      target_schema='gold',
      strategy='check',
      unique_key='item_id',
      check_cols=['canonical_name', 'brand', 'barcode', 'size_norm', 'coicop_division', 'coicop_code', 'is_active'],
    )
}}

select
    item_id,
    canonical_name,
    brand,
    barcode,
    size_norm,
    coicop_division,
    coicop_code,
    unit_of_measure,
    store_count,
    avg_match_confidence,
    first_seen,
    last_seen,
    is_active,
    now() as updated_at
from {{ ref('dim_items') }}

{% endsnapshot %}
