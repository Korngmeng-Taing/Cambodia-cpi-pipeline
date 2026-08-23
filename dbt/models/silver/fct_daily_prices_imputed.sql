-- fct_daily_prices_imputed
-- Daily fact with gap-filling: an item missing on date t is carried forward at
-- the most recent observed price for up to 7 consecutive days (is_imputed=TRUE,
-- gap_days tracks the carry distance).
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scrape_date', 'store_slug', 'item_id'],
    on_schema_change='append_new_columns'
) }}

with date_range as (
    select
        {% if is_incremental() %}
            coalesce(max(scrape_date) - interval '7 days', '2020-01-01'::date)::date as start_date,
            coalesce(max(scrape_date), current_date) as end_date
        {% else %}
            coalesce(min(scrape_date), '2020-01-01'::date) as start_date,
            coalesce(max(scrape_date), current_date) as end_date
        {% endif %}
    from {{ ref('fct_daily_prices') }}
),
base as (
    select scrape_date, store_slug, item_id, price_khr, unit_price_khr, coicop_division
    from {{ ref('fct_daily_prices') }}
    where scrape_date >= (select start_date from date_range)
),
calendar as (
    select d::date as scrape_date
    from date_range r,
    generate_series(r.start_date, r.end_date, interval '1 day') as d
),
store_items as (
    select distinct store_slug, item_id from base
),
sparse as (
    select
        c.scrape_date,
        si.store_slug,
        si.item_id,
        b.price_khr,
        b.unit_price_khr,
        b.coicop_division
    from calendar c
    cross join store_items si
    left join base b
        on b.scrape_date = c.scrape_date
       and b.store_slug = si.store_slug
       and b.item_id = si.item_id
),
grp as (
    select
        sparse.*,
        count(price_khr) over (
            partition by store_slug, item_id order by scrape_date
        ) as fill_group
    from sparse
),
carried as (
    select
        grp.*,
        first_value(price_khr) over (
            partition by store_slug, item_id, fill_group order by scrape_date
        ) as carried_price_khr,
        first_value(unit_price_khr) over (
            partition by store_slug, item_id, fill_group order by scrape_date
        ) as carried_unit_price_khr,
        first_value(coicop_division) over (
            partition by store_slug, item_id, fill_group order by scrape_date
        ) as carried_coicop_division,
        case when price_khr is null
             then row_number() over (
                partition by store_slug, item_id, fill_group order by scrape_date
             ) - 1
             else 0
        end as gap_days
    from grp
)
select
    scrape_date,
    store_slug,
    item_id,
    coalesce(price_khr, carried_price_khr) as price_khr,
    coalesce(unit_price_khr, carried_unit_price_khr) as unit_price_khr,
    coalesce(coicop_division, carried_coicop_division) as coicop_division,
    (price_khr is null) as is_imputed,
    gap_days
from carried
where (price_khr is not null or (carried_price_khr is not null and gap_days <= 7))
{% if is_incremental() %}
  and scrape_date >= (select start_date from date_range)
{% endif %}
