-- test_coicop_coverage
-- Every non-UNCLASSIFIED division used by the classifier must exist in the
-- official weights reference (category_weights seed / dim_coicop_hierarchy).
select
    c.item_id,
    c.store_slug,
    c.canonical_name,
    c.coicop_division,
    c.coicop_method
from {{ ref('int_coicop_classified') }} c
where c.coicop_division not in ('UNCLASSIFIED', 'REVIEW')
  and c.coicop_division not in (
      '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'
  )
