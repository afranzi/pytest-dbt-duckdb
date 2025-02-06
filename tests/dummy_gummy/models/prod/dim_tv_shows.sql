with shows as (
    select *
    from {{ ref('int_show') }}
),

final as (
    select
        show_id,
        title,
        director,
        show_cast,
        countries,
        date_added,
        release_year,
        rating_id,
        rating_name,
        only_adults,
        min_age,
        duration as seasons,
        listed_in
    from shows
    where show_type = 'TV Show'
)

select *
from final
