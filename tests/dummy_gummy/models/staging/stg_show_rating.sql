with source as (
    select *
    from {{ ref('seed_show_rating') }}
),

final as (
    select
        rating_id,
        rating_name,
        only_adults,
        min_age
    from source
)

select *
from final
