from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.document import DocumentCreate


async def create_document(
    session: AsyncSession,
    user_id: int,
    data: DocumentCreate,
) -> Document:
    document = Document(
        user_id=user_id,
        transaction_id=data.transaction_id,
        telegram_file_id=data.telegram_file_id,
        local_path=data.local_path,
        file_hash=data.file_hash,
        mime_type=data.mime_type,
        file_size_bytes=data.file_size_bytes,
        status=data.status,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def get_last_documents(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[Document]:
    bounded_limit = max(0, min(limit, 20))
    result = await session.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .limit(bounded_limit)
    )
    return list(result.scalars().all())
