from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Final, TypeAlias

from src.core.exceptions import ExtractionError
from src.schemas.documents import MimeType

ExtractorFunc: TypeAlias = Callable[[BytesIO], str]


class TextExtractor:
    def __init__(self):
        self.extractors: Final[dict[MimeType, ExtractorFunc]] = {
            MimeType.txt: self._extract_txt,
            MimeType.docx: self._extract_docx,
            MimeType.xlsx: self._extract_xlsx,
            MimeType.pdf: self._extract_pdf,
        }

    def extract(self, temp_filename: Path | str, mime_type: MimeType) -> str:
        """Extracts the text of the uploaded file"""
        extractor = self.extractors.get(mime_type)
        if not extractor:
            raise ExtractionError(
                error_code="invalid_mime_type",
                log_context={"mime_type": mime_type},
            )
        file = None
        try:
            file = self._get_file_data(temp_filename)
            file.seek(0)
            text = extractor(file)
        finally:
            if file is not None:
                file.close()
        return text

    def _get_file_data(self, temp_filename: Path | str) -> BytesIO:
        """Reads the uploaded file and returns the data"""
        path = Path(temp_filename)
        if not path.is_file():
            raise ExtractionError(
                error_code="file_not_found",
                log_context={"path": path},
            )

    def _extract_txt(self, file: BytesIO) -> str:
        pass

    def _extract_docx(self, file: BytesIO) -> str:
        pass

    def _extract_xlsx(self, file: BytesIO) -> str:
        pass

    def _extract_pdf(self, file: BytesIO) -> str:
        pass
