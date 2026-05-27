from datetime import datetime

from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    telegram_user_id: int
    name: str | None
    created_at: datetime
