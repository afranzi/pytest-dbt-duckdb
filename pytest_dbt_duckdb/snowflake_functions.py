from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta


def to_char(dt: datetime, fmt: str) -> str | None:
    if not dt:
        return None
    fmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
    return dt.strftime(fmt)


def date_add(unit: str, value: int, timestamp: datetime) -> datetime:
    unit = unit.lower()

    if unit == "second":
        return timestamp + timedelta(seconds=value)
    elif unit == "minute":
        return timestamp + timedelta(minutes=value)
    elif unit == "hour":
        return timestamp + timedelta(hours=value)
    elif unit == "day" or unit == "days":
        return timestamp + timedelta(days=value)
    elif unit == "week":
        return timestamp + timedelta(weeks=value)
    elif unit == "month":
        return timestamp + relativedelta(months=value)
    elif unit == "year":
        return timestamp + relativedelta(years=value)
    else:
        raise ValueError(f"Unsupported unit: {unit}")


def iff() -> str:
    return """
        CREATE MACRO IF NOT EXISTS iff(condition, true_value, false_value) AS (
            CASE
                WHEN condition THEN true_value
                ELSE false_value
            END
        );
    """


def bitand() -> str:
    return "CREATE MACRO IF NOT EXISTS BITAND(a, b) AS (a & b);"


def array_size() -> str:
    return """
        CREATE MACRO IF NOT EXISTS array_size(arr) AS (
            CASE
                WHEN arr IS NULL THEN NULL
                ELSE ARRAY_LENGTH(arr)
            END
        );
    """


def array_union_agg() -> str:
    return """
        CREATE MACRO IF NOT EXISTS array_union_agg(field) AS (
            list_distinct(flatten(list(field)))
        );
    """


def to_decimal() -> str:
    return """
        CREATE MACRO IF NOT EXISTS to_decimal(expr, precision, scale) AS (
            CAST(expr as DECIMAL(12,5))
        );
    """


def div0() -> str:
    return """
        CREATE MACRO IF NOT EXISTS div0(numerator, denominator) AS (
            CASE
                WHEN denominator = 0 THEN 0
                ELSE numerator / denominator
            END
        );
    """


def current_timestamp() -> str:
    return """
        CREATE MACRO IF NOT EXISTS current_timestamp() AS (
            current_localtimestamp()
        );
    """
