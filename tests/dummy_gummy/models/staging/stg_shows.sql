with source as (
    select *
    from {{ source('raw', 'shows')}}
),

final as (
    select
        show_id,
        type as show_type,
        title,
        director,
        string_split("cast", ', ') as show_cast,
        string_split(country, ', ') as countries,
        strptime(date_added, '%B %-d, %Y')::date as date_added,
        release_year::int as release_year,
        rating as rating_id,
        regexp_extract(duration, '[\d]+')::int as duration,
        string_split(listed_in, ', ') as listed_in,
        description
    from source
)

select *
from final
