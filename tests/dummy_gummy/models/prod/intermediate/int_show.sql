with shows as (
    select *
    from {{ ref('stg_shows') }}
),

show_rating as (
    select *
    from {{ ref('stg_show_rating') }}
),

final as (
    select
        shows.show_id,
        shows.show_type,
        shows.title,
        shows.director,
        shows.show_cast,
        shows.countries,
        shows.date_added,
        shows.release_year,
        show_rating.rating_id,
        show_rating.rating_name,
        show_rating.only_adults,
        show_rating.min_age,
        shows.duration,
        shows.listed_in
    from shows
    join show_rating on (shows.rating_id = show_rating.rating_id)
)

select *
from final
