from datetime import datetime, timezone


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def percentile(sorted_values, target):
    count = len(sorted_values)
    if count == 0:
        return None
    low, high = 0, count
    while low < high:
        middle = (low + high) >> 1
        if sorted_values[middle] < target:
            low = middle + 1
        else:
            high = middle
    return low / count
