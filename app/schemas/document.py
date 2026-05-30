from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    transaction_id: int | None = None
    telegram_file_id: str
    local_path: str
    file_hash: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    status: Literal["uploaded"] = "uploaded"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    transaction_id: int | None
    telegram_file_id: str
    local_path: str
    file_hash: str
    mime_type: str | None
    file_size_bytes: int | None
    status: str
    ocr_status: str
    ocr_text: str | None
    ocr_processed_at: datetime | None
    created_at: datetime
    updated_at: datetime
