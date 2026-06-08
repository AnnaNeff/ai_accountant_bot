from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.01")


def calculate_vat_from_gross(
    gross_amount: Decimal,
    vat_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    net_amount = (gross_amount / (Decimal("1") + vat_rate)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    vat_amount = (gross_amount - net_amount).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return net_amount, vat_amount
