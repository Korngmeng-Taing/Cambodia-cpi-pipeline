-- test_utility_tariffs
-- Regulated EDC electricity + PPWSA water tariffs must be sane: positive rates,
-- exactly two representative tariffs (one per utility), valid effective dates.
with bad_rows as (
    select source_name, service_type, rate_khr, unit, is_representative, effective_from
    from {{ ref('utility_tariffs') }}
    where rate_khr <= 0
       or effective_from is null
       or effective_from::date > current_date
       or is_representative not in ('TRUE', 'FALSE')
)
select * from bad_rows
union all
select
    'representative-count' as source_name,
    'electricity' as service_type,
    0 as rate_khr,
    '' as unit,
    'TRUE' as is_representative,
    '2020-01-01' as effective_from
from {{ ref('utility_tariffs') }}
where is_representative = 'TRUE' and source_name = 'edc'
having count(*) <> 1
union all
select
    'representative-count' as source_name,
    'water' as service_type,
    0 as rate_khr,
    '' as unit,
    'TRUE' as is_representative,
    '2020-01-01' as effective_from
from {{ ref('utility_tariffs') }}
where is_representative = 'TRUE' and source_name = 'ppwsa'
having count(*) <> 1
