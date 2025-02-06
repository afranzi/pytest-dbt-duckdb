with shows as (
    select *
    from {{ ref('int_show') }}
),

show_cast as (
    select
        show_id,
        show_type,
        title,
        director,
        actor_name,
        release_year,
        rating_id,
        countries,
        case show_type when 'Movie' then duration end as movie_duration,
        case show_type when 'TV Show' then duration end as tv_show_seasons,
        only_adults
    from shows
    left join unnest(show_cast) as actors(actor_name) on true
),

final as (
    select
        actor_name,
        count(distinct show_id)::int as shows,
        count(distinct case when only_adults then show_id end)::int as only_adult_shows,
        count(distinct case show_type when 'Movie' then show_id end)::int as movies,
        count(distinct case show_type when 'TV Show' then show_id end)::int as tv_shows,
        min(release_year) as first_show,
        max(release_year) as last_show,
        sum(movie_duration)::int as total_movie_duration,
        sum(tv_show_seasons)::int as tv_show_seasons,
        list_sort(array_agg(distinct rating_id)) as ratings
    from show_cast
    group by 1
)

select *
from final
