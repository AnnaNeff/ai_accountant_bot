from decimal import Decimal

from app.tax.israel.vat import calculate_vat_from_gross


def test_calculate_vat_from_gross_uses_decimal_and_rounds_to_cents() -> None:
    net_amount, vat_amount = calculate_vat_from_gross(
        Decimal("118.00"),
        Decimal("0.18"),
    )

    assert net_amount == Decimal("100.00")
    assert vat_amount == Decimal("18.00")
    assert isinstance(net_amount, Decimal)
    assert isinstance(vat_amount, Decimal)
