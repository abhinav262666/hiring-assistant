import io
from typing import Optional
import logging

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

from settings import senv

logger = senv.backend_logger


class OCRService:
    """Service for extracting text from various file formats."""

    @staticmethod
    def extract_text_from_file(file_content: bytes, filename: str) -> str:
        """
        Extract text from uploaded file.

        Args:
            file_content: Raw file bytes
            filename: Original filename to determine file type

        Returns:
            Extracted text content

        Raises:
            ValueError: If file type is unsupported or extraction fails
        """
        if not filename:
            raise ValueError("Filename is required to determine file type")

        file_extension = filename.split('.')[-1].lower()

        if file_extension == 'pdf':
            return OCRService._extract_text_from_pdf(file_content)
        elif file_extension in ['txt', 'md']:
            return OCRService._extract_text_from_text(file_content)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")

    @staticmethod
    def _extract_text_from_pdf(file_content: bytes) -> str:
        """Extract text from PDF file."""
        if PdfReader is None:
            raise ValueError("PyPDF2 is not installed. Please install it to process PDF files.")

        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PdfReader(pdf_file)

            text_content = []
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text.strip():
                    text_content.append(text.strip())

            extracted_text = '\n\n'.join(text_content)

            if not extracted_text.strip():
                raise ValueError("No text could be extracted from the PDF")

            logger.info(f"Successfully extracted {len(extracted_text)} characters from PDF")
            return extracted_text

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {str(e)}")
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")

    @staticmethod
    def _extract_text_from_text(file_content: bytes) -> str:
        """Extract text from plain text file."""
        try:
            text = file_content.decode('utf-8')
            logger.info(f"Successfully extracted {len(text)} characters from text file")
            return text
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode text file: {str(e)}")
            raise ValueError(f"Failed to decode text file: {str(e)}")

    @staticmethod
    def is_supported_filetype(filename: str) -> bool:
        """Check if the file type is supported for text extraction."""
        if not filename:
            return False

        supported_extensions = {'pdf', 'txt', 'md'}
        file_extension = filename.split('.')[-1].lower()
        return file_extension in supported_extensions
