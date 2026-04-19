from verify import contains_high_school, parse_deadline


def test_parse_deadline_month_day_year():
    assert parse_deadline("March 15, 2026") == "2026-03-15"


def test_contains_high_school_phrase():
    assert contains_high_school("Open to high school juniors and seniors")
