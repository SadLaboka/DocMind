from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Enum, Text
import enum

from src.models.base import Base


class DocumentStatus(enum.Enum):
    created = "created"
    queued = "queued"
    processing = "processing"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class Documents(Base):
    __tablename__ = "documents"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str]
    file_size: Mapped[str]
    file_hash: Mapped[str]
    task_id: Mapped[int]
    document_text: Mapped[str]
    document_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.created
    )
    error_trace: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    analyse: Mapped[str] = mapped_column(Text, nullable=True, default=None)
