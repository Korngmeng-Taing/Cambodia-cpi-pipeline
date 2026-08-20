-- test_bookmebus_redbus_coicop_07
-- Asserts that 100% of tickets from BookMeBus and RedBus map exclusively to COICOP 07 (Transport).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('bookmebus', 'redbus', 'redmebus')
  and coicop_division <> '07'
