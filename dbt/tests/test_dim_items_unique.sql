-- test_dim_items_unique
-- The Silver canonical item dimension must be unique by item_id and have
-- a non-empty canonical_name for every row.
with invalid_nulls as (
    select
        item_id,
        canonical_name,
        'null_or_empty' as issue_type
    from {{ ref('dim_items') }}
    where canonical_name is null
       or trim(canonical_name) = ''
       or item_id is null
       or item_id = ''
),
duplicates as (
    select
        item_id,
        min(canonical_name) as canonical_name,
        'duplicate_item_id' as issue_type
    from {{ ref('dim_items') }}
    where item_id is not null and item_id != ''
    group by item_id
    having count(*) > 1
)
select * from invalid_nulls
union all
select * from duplicates
