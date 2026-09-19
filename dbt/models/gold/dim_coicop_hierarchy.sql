-- dim_coicop_hierarchy
-- Mapping of all observed COICOP codes to their hierarchical parents
-- Used for drill-down reporting in BI tools.
{{ config(
    materialized='table'
) }}

with all_codes as (
    select distinct coicop_code as code
    from {{ source('gold', 'fct_elementary_indices') }}
    where coicop_code is not null
)
select
    code,
    split_part(code, '.', 1) as division,
    case 
        when length(code) > 3 then split_part(code, '.', 1) || '.' || split_part(code, '.', 2)
        else null 
    end as group_code,
    case 
        when length(code) > 5 and split_part(code, '.', 3) != '' then split_part(code, '.', 1) || '.' || split_part(code, '.', 2) || '.' || split_part(code, '.', 3)
        else null 
    end as class_code,
    case 
        when code ~ '^\d{2}\.\d{1,2}\.\d{1,2}\.\d{1,2}$' then code
        else null 
    end as subclass_code
from all_codes
