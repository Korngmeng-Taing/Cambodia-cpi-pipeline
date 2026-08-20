-- test_weights_sum_to_100
-- Asserts that the official 12-division category weights sum to exactly 100.000%
-- (within float rounding tolerance of 0.01).
with total as (
    select sum(weight_pct) as sum_weight_pct
    from {{ ref('category_weights') }}
)
select sum_weight_pct
from total
where abs(sum_weight_pct - 100.0) > 0.01
