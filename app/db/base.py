from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import mapped classes so Alembic receives complete Base.metadata.
from app.models import (  # noqa: E402, F401
    document,
    financial_profile,
    obligation_payment,
    recurring_rule,
    transaction,
    user,
)
