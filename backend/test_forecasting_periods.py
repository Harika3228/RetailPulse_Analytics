from backend.controllers.forecasting_controller import _resolve_forecast_period


def test_resolve_next_7_days_period() -> None:
    label, days = _resolve_forecast_period("7d")
    assert label == "Next 7 Days"
    assert days == 7


def test_resolve_custom_period_from_dates() -> None:
    label, days = _resolve_forecast_period("custom", "2026-07-01", "2026-07-10")
    assert label == "Custom Date Range"
    assert days == 9
