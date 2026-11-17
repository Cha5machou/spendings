from datetime import date

from app.routers.actions import day_in_month, euro, horizon_for, month_name, signed, typical_day


def test_horizon_follows_the_date():
    today = date(2026, 11, 17)
    assert horizon_for(date(2026, 11, 20), today) == "week"
    assert horizon_for(date(2026, 12, 10), today) == "month"
    assert horizon_for(date(2027, 1, 20), today) == "quarter"
    assert horizon_for(date(2027, 8, 1), today) == "year"


def test_day_in_month_clips_to_month_length():
    assert day_in_month(2027, 2, 31) == date(2027, 2, 28)
    assert day_in_month(2026, 11, 29) == date(2026, 11, 29)


def test_typical_day_is_the_median():
    assert typical_day([date(2026, 7, 27), date(2026, 8, 31), date(2026, 9, 29), date(2026, 10, 28)]) == 28
    assert typical_day([]) is None


def test_money_formatting_keeps_the_sign_where_it_matters():
    assert euro(-1162.4) == "1 162 €"
    assert signed(-1162.4) == "-1 162 €"
    assert signed(357) == "357 €"
    assert month_name("2027-02") == "February 2027"
