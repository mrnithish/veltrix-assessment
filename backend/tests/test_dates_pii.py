from datetime import date

from app.data.repositories import Employee
from app.observability.pii import mask_email, mask_for_user, register_people, scrub_for_logs
from app.orchestration.agent import has_leave_type_cue, is_confirmation
from app.orchestration.dates import resolve_dates

TODAY = date(2026, 6, 15)  # Monday


def test_next_week_is_monday_to_friday_of_following_week():
    assert resolve_dates("next week", TODAY) == {"start_date": "2026-06-22", "end_date": "2026-06-26"}


def test_next_friday_is_first_friday_after_today():
    assert resolve_dates("next friday", TODAY)["start_date"] == "2026-06-19"
    friday = date(2026, 6, 19)
    assert resolve_dates("next friday", friday)["start_date"] == "2026-06-26"


def test_date_without_year_means_2026_and_ranges():
    assert resolve_dates("3 to 5 july", TODAY) == {"start_date": "2026-07-03", "end_date": "2026-07-05"}
    assert resolve_dates("July 20", TODAY)["start_date"] == "2026-07-20"


def test_past_date_is_flagged():
    assert "error" in resolve_dates("1 june", TODAY)


def test_mask_email():
    assert mask_email("priya.nair@veltrix.example") == "p***@veltrix.example"


def test_answers_mask_emails_drop_phones_and_hide_names():
    register_people([Employee("E9", "Zed Quinn", "zed.quinn@veltrix.example", "+91 98450 99999", "IN",
                              "2020-01-01", "L1", "employee", None)])
    text = "Contact Zed Quinn at zed.quinn@veltrix.example or +91 98450 99999 on 2026-06-15."
    out = mask_for_user(text, visible_names=set())
    assert "z***@veltrix.example" in out and "98450" not in out and "Zed Quinn" not in out
    assert "2026-06-15" in out
    assert "Zed Quinn" in mask_for_user(text, visible_names={"Zed Quinn"})


def test_logs_never_contain_names_emails_or_phones():
    register_people([Employee("E9", "Zed Quinn", "zed.quinn@veltrix.example", "+91 98450 99999", "IN",
                              "2020-01-01", "L1", "employee", None)])
    out = scrub_for_logs("Zed Quinn zed.quinn@veltrix.example +91 98450 99999")
    assert "Zed" not in out and "zed.quinn" not in out and "99999" not in out and "E9" in out


def test_confirmation_detection():
    for msg in ("yes", "Yes!", "confirm", "go ahead", "yes please", "ok, go ahead", "Yes, confirm it"):
        assert is_confirmation(msg), msg
    for msg in ("no", "make it until Friday instead", "yes but change it to 3 July", "what is my balance?",
                "don't", "wait"):
        assert not is_confirmation(msg), msg


def test_leave_type_cues():
    assert has_leave_type_cue(["book a vacation next week"], "annual")
    assert has_leave_type_cue(["I'm sick tomorrow"], "sick")
    assert not has_leave_type_cue(["I need Friday off"], "annual")


def test_past_reference_date_from_message():
    from app.orchestration.dates import past_reference_date

    assert past_reference_date("What was the sick leave allowance in 2025?", TODAY) == date(2025, 12, 31)
    assert past_reference_date("What applied on 1 August 2025?", TODAY) == date(2025, 8, 1)
    assert past_reference_date("Book leave on 4 December", TODAY) is None
    assert past_reference_date("What changes in 2027?", TODAY) is None
