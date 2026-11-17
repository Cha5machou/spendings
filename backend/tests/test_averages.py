from app.routers.insights import averaging_months

TWELVE = 12


def test_a_new_recurring_payment_is_averaged_from_its_first_month():
    rent = [0.0] * 8 + [1116.74, 1067.0, 1034.0, 999.03]
    assert averaging_months(rent, TWELVE) == 4


def test_a_catch_up_first_month_extends_the_start_by_one_month():
    # first salary arrives late: December holds November and December
    salary = [0.0, 7772.0, 0.0, 3847.0, 3847.0, 3847.0, 3780.0, 3780.0, 4065.0, 3782.0, 3748.0, 3747.0]
    assert averaging_months(salary, TWELVE) == 12


def test_a_sporadic_payment_keeps_the_whole_window():
    tax = [0.0] * 9 + [565.0, 565.0, 0.0]
    assert averaging_months(tax, TWELVE) == 12


def test_a_category_present_all_year_keeps_the_whole_window():
    assert averaging_months([300.0] * 12, TWELVE) == 12


def test_a_single_appearance_is_not_a_habit():
    assert averaging_months([0.0] * 11 + [800.0], TWELVE) == 12


def test_a_three_month_old_subscription_present_every_month_is_shortened():
    assert averaging_months([0.0] * 9 + [10.0, 10.0, 10.0], TWELVE) == 3
