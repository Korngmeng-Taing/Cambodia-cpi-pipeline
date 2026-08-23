-- test_communitypharma_coicop_06
-- Asserts that 100% of items from communitypharma and pharmacy stores map exclusively to COICOP 06 (Health).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('communitypharma')
  and coicop_division <> '06'
