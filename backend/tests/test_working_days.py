from datetime import date

from app.tools.working_days import applicable_calendar, count_working_days, public_holidays
from tests.conftest import make_ctx


def d(s: str) -> date:
    return date.fromisoformat(s)


def test_weekdays_only():
    # Mon 2026-06-15 .. Sun 2026-06-21: five weekdays
    assert count_working_days(d("2026-06-15"), d("2026-06-21"), set()) == 5


def test_weekend_only_range_is_zero():
    assert count_working_days(d("2026-06-20"), d("2026-06-21"), set()) == 0


def test_single_day():
    assert count_working_days(d("2026-06-16"), d("2026-06-16"), set()) == 1


def test_holiday_on_weekday_is_excluded():
    assert count_working_days(d("2026-06-15"), d("2026-06-19"), {d("2026-06-19")}) == 4


def test_holiday_on_weekend_changes_nothing():
    assert count_working_days(d("2026-08-10"), d("2026-08-16"), {d("2026-08-15")}) == 5


def test_range_spanning_weekend_and_holiday():
    # Thu 18 Jun .. Tue 23 Jun: Thu, (Fri holiday), Mon, Tue -> 3
    assert count_working_days(d("2026-06-18"), d("2026-06-23"), {d("2026-06-19")}) == 3


def test_end_before_start_is_zero():
    assert count_working_days(d("2026-06-19"), d("2026-06-18"), set()) == 0


def test_region_calendar_from_ingested_documents(corpus):
    ctx = make_ctx("E201", corpus)  # India
    hols = public_holidays(corpus.docs, corpus.holidays, ctx.requester, d("2026-06-15"), d("2026-06-30"))
    assert set(hols) == {d("2026-06-19")}  # restricted holiday on 17 June is not a day off


def test_india_2026_calendar_wins_over_2025_for_2026(corpus):
    ctx = make_ctx("E201", corpus)
    assert applicable_calendar(corpus.docs, corpus.holidays, ctx.requester, 2026).doc_id == "CAL-IN-2026"


def test_other_region_holidays_do_not_apply(corpus):
    ctx = make_ctx("E301", corpus)  # Germany: 19 June is a normal working day
    hols = public_holidays(corpus.docs, corpus.holidays, ctx.requester, d("2026-06-15"), d("2026-06-30"))
    assert hols == {}
    de = public_holidays(corpus.docs, corpus.holidays, ctx.requester, d("2026-05-25"), d("2026-05-25"))
    assert d("2026-05-25") in de
