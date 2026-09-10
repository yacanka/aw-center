"""Timeline builders for compliance-document dashboard analytics."""

from datetime import datetime


def build_timeline(scheduled, actual, total, today):
    """Return deterministic remaining-document series and reference points."""

    scheduled_points = _remaining_series(scheduled, total)
    actual_points = _remaining_series(actual, total)
    today_point = {"x": _format_date(today), "y": _remaining_on(actual, total, today)}
    return {
        "scheduled": scheduled_points,
        "actual": _with_today(actual_points, today_point),
        "today": [today_point],
        "last_scheduled": _latest_on_or_before(scheduled_points, today),
        "last_actual": _latest_on_or_before(actual_points, today),
    }


def _remaining_series(counter, total):
    remaining = total
    result = []
    for event_date, count in sorted(counter.items()):
        remaining -= count
        result.append({"x": _format_date(event_date), "y": remaining})
    return result


def _remaining_on(counter, total, target):
    return total - sum(count for event_date, count in counter.items() if event_date <= target)


def _with_today(points, today_point):
    points = [point for point in points if point["x"] != today_point["x"]]
    points.append(today_point)
    return sorted(points, key=lambda point: _parse_date(point["x"]))


def _latest_on_or_before(points, target):
    eligible = [point for point in points if _parse_date(point["x"]) <= target]
    return eligible[-1] if eligible else None


def _parse_date(value):
    return datetime.strptime(value, "%d.%m.%Y").date()


def _format_date(value):
    return value.strftime("%d.%m.%Y")
