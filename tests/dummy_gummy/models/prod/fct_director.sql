with shows as (
    select *
    from {{ ref('int_show') }}
),

director as (
    select
        show_id,
        show_type,
        title,
        director,
        release_year,
        rating_id,
        show_cast,
        countries,
        only_adults,
        case show_type when 'Movie' then duration end as movie_duration,
        case show_type when 'TV Show' then duration end as tv_show_seasons,
    from shows
    where director is not null
),

director_cast as (
    select
        director,
        actor_name,
    from director
    left join unnest(show_cast) as actors(actor_name) on true
),

director_country as (
    select
        director,
        country,
    from director
    left join unnest(countries) as countries(country) on true
),

final as (
    select
        director.director,
        count(distinct show_id)::int as shows,
        count(distinct case when only_adults then show_id end)::int as only_adult_shows,
        count(distinct case show_type when 'Movie' then show_id end)::int as movies,
        count(distinct case show_type when 'TV Show' then show_id end)::int as tv_shows,
        min(release_year) as first_show,
        max(release_year) as last_show,
        list_sort(list_distinct(array_agg(distinct rating_id))) as ratings,
        list_sort(list_distinct(array_agg(distinct country))) as countries,
        list_sort(list_distinct(array_agg(distinct actor_name))) as actors,
    from director
    left join director_cast on (director.director = director_cast.director)
    left join director_country on (director.director = director_country.director)
    group by 1
)

select *
from final
