from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import mapped classes so Alembic receives complete Base.metadata.
from app.models import document, financial_profile, recurring_rule, transaction, user  # noqa: E402, F401
