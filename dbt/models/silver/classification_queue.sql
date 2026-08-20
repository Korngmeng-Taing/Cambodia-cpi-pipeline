-- classification_queue
-- Appends REVIEW / UNCLASSIFIED daily-fact rows to silver.classification_queue.
-- The table is owned by sql/schema.sql (id BIGSERIAL + labeling_app contract);
-- this model only appends NEW pending rows so re-runs do not duplicate and
-- historical RESOLVED rows are never touched.
{{ config(
    materialized='incremental',
    strategy='append',
    on_schema_change='append_new_columns'
) }}

with candidates as (
    select
        p.item_id::text as product_key,
        p.store_slug,
        min(p.name_clean) as name_clean,
        mode() within group (order by p.category_native) as category_native,
        round(exp(avg(ln(p.price_khr)) filter (where p.price_khr > 0)), 2) as price_khr,
        case when p.coicop_division = 'REVIEW' then 'low confidence'
             else 'unclassified'
        end as reason,
        'PENDING'::varchar(32) as status,
        now() as created_at
    from {{ ref('fct_daily_prices') }} p
    where p.coicop_division in ('REVIEW', 'UNCLASSIFIED')
    group by p.item_id::text, p.store_slug, p.coicop_division
)
select
    c.product_key,
    c.store_slug,
    c.name_clean,
    c.category_native,
    c.price_khr,
    c.reason,
    c.status,
    c.created_at
from candidates c
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} q
    where q.status = 'PENDING'
      and q.product_key = c.product_key
      and q.store_slug = c.store_slug
)
{% endif %}
