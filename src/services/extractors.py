from src.schemas.documents import MimeType


def extract_text():
    pass


def _extract_txt():
    pass


def _extract_docx():
    pass


def _extract_xlsx():
    pass


def _extract_pdf():
    pass


extractor = {
    MimeType.txt: _extract_txt,
    MimeType.docx: _extract_docx,
    MimeType.xlsx: _extract_xlsx,
    MimeType.pdf: _extract_pdf
}
