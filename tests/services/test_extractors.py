import pytest
from io import BytesIO
from pathlib import Path

from src.core.exceptions import ExtractionError
from src.schemas.documents import MimeType
from src.services.extractors import TextExtractor
from tests.conftest import FIXTURES_DIR

FIXTURES_DIR = FIXTURES_DIR / "documents"


def test_extract_txt_success():
    text_extractor = TextExtractor()
    test_file_data = BytesIO((FIXTURES_DIR / "test.txt").read_bytes())
    result = text_extractor._extract_txt(test_file_data)
    assert isinstance(result, str)
    assert "Test test test" in result


def test_extract_txt_invalid_encoding():
    text_extractor = TextExtractor()
    test_file_data = BytesIO(b"\xff\xfe\x00\x00")
    result = text_extractor._extract_txt(test_file_data)
    assert isinstance(result, str)


def test_extract_txt_empty():
    text_extractor = TextExtractor()
    test_file_data = BytesIO(b"")
    result = text_extractor._extract_txt(test_file_data)
    assert result == ""


def test_extract_docx_success():
    text_extractor = TextExtractor()
    test_file_data = BytesIO((FIXTURES_DIR / "test.docx").read_bytes())
    result = text_extractor._extract_docx(test_file_data)
    assert isinstance(result, str)


def test_extract_xlsx_success():
    text_extractor = TextExtractor()
    test_file_data = BytesIO((FIXTURES_DIR / "test.xlsx").read_bytes())
    result = text_extractor._extract_xlsx(test_file_data)
    assert isinstance(result, str)
    assert "Sheet" in result


def test_extract_pdf_success():
    text_extractor = TextExtractor()
    test_file_data = BytesIO((FIXTURES_DIR / "test.pdf").read_bytes())
    result = text_extractor._extract_pdf(test_file_data)
    assert isinstance(result, str)
    assert "Page" in result


def test_get_file_data_not_found():
    text_extractor = TextExtractor()
    with pytest.raises(ExtractionError) as exc_info:
        text_extractor._get_file_data("/nonexistent/path/to/file.txt")
    assert exc_info.value.error_code == "file_not_found"
    assert "path" in exc_info.value.log_context


def test_extract_invalid_mime_type():
    text_extractor = TextExtractor()
    test_file = FIXTURES_DIR / "test.txt"

    class FakeMimeType:
        value = "fake/type"

    with pytest.raises(ExtractionError) as exc_info:
        text_extractor.extract(test_file, FakeMimeType())

    assert exc_info.value.error_code == "invalid_mime_type"
    assert "mime_type" in exc_info.value.log_context


def test_extract_corrupted_pdf(tmp_path):
    text_extractor = TextExtractor()
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("This is not a real PDF file")

    with pytest.raises(ExtractionError) as exc_info:
        text_extractor.extract(fake_pdf, MimeType.pdf)
    assert exc_info.value.error_code == "invalid_file"
    assert "detail" in exc_info.value.log_context


def test_extract_corrupted_docx(tmp_path):
    text_extractor = TextExtractor()
    fake_docx = tmp_path / "fake.docx"
    fake_docx.write_text("This is not a real DOCX file")

    with pytest.raises(ExtractionError) as exc_info:
        text_extractor.extract(fake_docx, MimeType.docx)
    assert exc_info.value.error_code == "invalid_file"
    assert "detail" in exc_info.value.log_context


def test_extract_corrupted_xlsx(tmp_path):
    text_extractor = TextExtractor()
    fake_xlsx = tmp_path / "fake.xlsx"
    fake_xlsx.write_text("This is not a real XLSX file")

    with pytest.raises(ExtractionError) as exc_info:
        text_extractor.extract(fake_xlsx, MimeType.xlsx)
    assert exc_info.value.error_code == "invalid_file"
    assert "detail" in exc_info.value.log_context
