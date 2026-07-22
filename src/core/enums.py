from enum import Enum


class MimeType(Enum):
    txt = "text/plain"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    pdf = "application/pdf"


class DocumentStatus(Enum):
    created = "created"
    scanning = "scanning"
    extracting = "extracting"
    extracted = "extracted"
    analyzing = "analyzing"
    success = "success"
    infected = "infected"
    failed = "failed"
    cancelled = "cancelled"


class LLMProvider(Enum):
    gemini = "gemini"
    deepseek = "deepseek"
    kimi = "kimi"


class PromptType(Enum):
    document_analysis = "document_analysis"
