-- test_weights_sum_to_100
-- Asserts that the official 12-division category weights sum to exactly 100.000%
-- (within float rounding tolerance of 0.01).
with total as (
    select sum(weight_pct) as sum_weight_pct
    from {{ ref('cambodia_cpi_coicop_weights_breakdown') }}
    where coicop_level = 'Division'
)
select sum_weight_pct
from total
where abs(sum_weight_pct - 100.0) > 0.01
