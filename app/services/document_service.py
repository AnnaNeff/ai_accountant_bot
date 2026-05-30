from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.transaction import Transaction
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


async def get_document_by_id(
    session: AsyncSession,
    user_id: int,
    document_id: int,
) -> Document | None:
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    return result.scalars().first()


async def link_document_to_transaction(
    session: AsyncSession,
    user_id: int,
    document_id: int,
    transaction_id: int,
) -> Document | None:
    document = await get_document_by_id(session, user_id, document_id)
    if document is None:
        return None

    transaction_result = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )
    transaction = transaction_result.scalars().first()
    if transaction is None:
        return None

    document.transaction_id = transaction.id
    await session.commit()
    await session.refresh(document)
    return document


async def unlink_document_from_transaction(
    session: AsyncSession,
    user_id: int,
    document_id: int,
) -> Document | None:
    document = await get_document_by_id(session, user_id, document_id)
    if document is None:
        return None

    document.transaction_id = None
    await session.commit()
    await session.refresh(document)
    return document
