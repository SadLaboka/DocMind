from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import MimeType
from src.core.enums import DocumentStatus
from src.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(300), nullable=True, default=None)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[MimeType] = mapped_column(
        Enum(MimeType, name="mime_type", native_enum=False),
        nullable=False
    )
    file_size: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=True, default=None)
    task_id: Mapped[int] = mapped_column(Integer, nullable=True, default=None)
    temp_filename: Mapped[str] = mapped_column(String(64), nullable=True, default=None)
    document_text: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    document_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=False),
        default=DocumentStatus.created,
    )
    error_trace: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    analysis: Mapped[str] = mapped_column(Text, nullable=True, default=None)
