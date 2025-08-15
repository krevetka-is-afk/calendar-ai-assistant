import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.importer import importer_service
from app.core.schemas import ImportRequest, RawEvent


@pytest.mark.asyncio
async def test_days_limit_filters_events():
    tz = "Europe/Moscow"
    now = datetime.now(ZoneInfo(tz))
    week_start_date = now.date() - timedelta(days=now.weekday())
    week_start = datetime.combine(week_start_date, datetime.min.time(), ZoneInfo(tz))

    in_week = week_start + timedelta(days=1)
    before_week = week_start - timedelta(days=1)

    events = [
        RawEvent(
            calendar="cal",
            start=in_week.isoformat(),
            end=(in_week + timedelta(hours=1)).isoformat(),
            summary="inside",
        ),
        RawEvent(
            calendar="cal",
            start=before_week.isoformat(),
            end=(before_week + timedelta(hours=1)).isoformat(),
            summary="before",
        ),
    ]

    request = ImportRequest(
        events=events,
        timezone=tz,
        expand_recurring=False,
        horizon_days=30,
        days_limit=0,
    )

    response = await importer_service.import_events(request)

    assert len(response.events) == 1
    assert response.events[0].summary == "inside"