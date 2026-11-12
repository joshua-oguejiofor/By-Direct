"""
Dependencies for the analytics router.

Two responsibilities live here:
  1. Admin auth — we deliberately do NOT define a new auth mechanism.
     We import and reuse the app's existing one.
  2. Date-range resolution — turns `period=` / `start_date=` / `end_date=`
     query params into a concrete, timezone-aware [start, end) window plus
     the equivalent "previous period" window for growth comparisons.

Date range convention (stated explicitly per spec requirement):
  - All ranges are **[start, end)** — inclusive of `start`, EXCLUSIVE of `end`.
    This avoids the classic "23:59:59.999 vs 00:00:00 next day" off-by-one
    bug and composes cleanly with SQL `>= start AND < end`.
  - All computation happens in `DEFAULT_TZ` (app timezone), then the
    resulting boundaries are converted to UTC before being used in queries,
    because DB timestamps are assumed stored in UTC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import Query

from app.core.config import settings
from app.core.enums import Grouping, Period
from app.core.exceptions import BadRequestError

_TZ = ZoneInfo(settings.DEFAULT_TZ)


@dataclass(frozen=True)
class ResolvedRange:
    start: datetime          # UTC, inclusive
    end: datetime             # UTC, exclusive
    previous_start: datetime  # UTC, inclusive — equivalent prior period
    previous_end: datetime    # UTC, exclusive
    grouping: Grouping
    label: str                 # human-readable, used in cache keys


def _local_midnight(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=_TZ)


def _to_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


def _start_of_week(d: date) -> date:
    # Monday as start of week.
    return d - timedelta(days=d.weekday())


def _start_of_month(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def resolve_period(
    period: Period,
    start_date: date | None,
    end_date: date | None,
    now: datetime,
) -> ResolvedRange:
    
    today = now.astimezone(_TZ).date()

    if period == Period.CUSTOM:
        if start_date is None or end_date is None:
            raise BadRequestError(
                "start_date and end_date are required when period=custom"
            )
        if end_date < start_date:
            raise BadRequestError("end_date must not be before start_date")
        start = _local_midnight(start_date)
        end = _local_midnight(end_date + timedelta(days=1))  # exclusive upper bound
        span = end - start
        prev_end = start
        prev_start = start - span
        label = f"{start_date.isoformat()}:{end_date.isoformat()}"
        grouping = Grouping.DAY if span <= timedelta(days=62) else Grouping.MONTH
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), grouping, label)

    if period == Period.TODAY:
        start = _local_midnight(today)
        end = start + timedelta(days=1)
        prev_start = start - timedelta(days=1)
        prev_end = start
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "today")

    if period == Period.YESTERDAY:
        end = _local_midnight(today)
        start = end - timedelta(days=1)
        prev_end = start
        prev_start = start - timedelta(days=1)
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "yesterday")

    if period == Period.LAST_7_DAYS:
        end = _local_midnight(today) + timedelta(days=1)
        start = end - timedelta(days=7)
        prev_end = start
        prev_start = start - timedelta(days=7)
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "7d")

    if period == Period.LAST_30_DAYS:
        end = _local_midnight(today) + timedelta(days=1)
        start = end - timedelta(days=30)
        prev_end = start
        prev_start = start - timedelta(days=30)
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "30d")

    if period == Period.THIS_WEEK:
        wk_start = _start_of_week(today)
        start = _local_midnight(wk_start)
        end = start + timedelta(days=7)
        prev_start = start - timedelta(days=7)
        prev_end = start
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "this_week")

    if period == Period.THIS_MONTH:
        m_start = _start_of_month(today)
        start = _local_midnight(m_start)
        end = _local_midnight(_add_months(m_start, 1))
        prev_m_start = _add_months(m_start, -1)
        prev_start = _local_midnight(prev_m_start)
        prev_end = start
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "this_month")

    if period == Period.PREVIOUS_MONTH:
        this_m_start = _start_of_month(today)
        prev_m_start = _add_months(this_m_start, -1)
        start = _local_midnight(prev_m_start)
        end = _local_midnight(this_m_start)
        prev2_m_start = _add_months(prev_m_start, -1)
        prev_start = _local_midnight(prev2_m_start)
        prev_end = start
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.DAY, "previous_month")

    if period == Period.THIS_YEAR:
        y_start = date(today.year, 1, 1)
        start = _local_midnight(y_start)
        end = _local_midnight(date(today.year + 1, 1, 1))
        prev_start = _local_midnight(date(today.year - 1, 1, 1))
        prev_end = start
        return ResolvedRange(_to_utc(start), _to_utc(end), _to_utc(prev_start), _to_utc(prev_end), Grouping.MONTH, "this_year")

    raise BadRequestError(f"Unsupported period: {period}")

# This is set as a Query function inline with the request the use resolve_period as a helper function
async def get_date_range(
    period: Period = Query(Period.LAST_30_DAYS, description="Predefined period, or 'custom'"),  # noqa: B008
    start_date: date | None = Query(None, description="Required if period=custom"),  # noqa: B008
    end_date: date | None = Query(None, description="Required if period=custom"),  # noqa: B008
) -> ResolvedRange:

    return resolve_period(period, start_date, end_date, datetime.now(UTC))


def get_grouping_override(
    group_by: Grouping | None = Query(None, description="Override auto-selected grouping: day|week|month"),  # noqa: B008
) -> Grouping | None:
    return group_by
