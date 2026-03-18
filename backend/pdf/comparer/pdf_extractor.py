import re
import logging
import warnings
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

# Uyarıları gizle
warnings.filterwarnings("ignore", message=".*Cropbox.*")
warnings.filterwarnings("ignore", message=".*CropBox.*")
warnings.filterwarnings("ignore", message=".*cropbox.*")

logging.getLogger("pdfplumber").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError as e:
    HAS_PDFPLUMBER = False

try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


@dataclass
class TextLine:
    text: str
    page_number: int
    line_in_page: int


@dataclass
class PageContent:
    page_number: int
    text: str
    lines: List[str]
    word_count: int
    char_count: int


@dataclass
class PDFDocument:
    file_path: str
    total_pages: int
    pages: List[PageContent]
    metadata: Dict
    all_lines: List[TextLine] = field(default_factory=list)
    
    def get_all_text(self) -> str:
        return "\n".join(line.text for line in self.all_lines)
    
    def get_all_line_texts(self) -> List[str]:
        return [line.text for line in self.all_lines]


class PDFExtractor:
    def __init__(self):
        self.extraction_method = "pdfplumber"
    
    def _process_pages(self, pages_data: List[Tuple[int, str]]) -> Tuple[List[PageContent], List[TextLine]]:
        page_contents = []
        all_lines = []
        
        for page_num, text in pages_data:
            lines = text.split('\n') if text else []
            clean_lines = [line.strip() for line in lines if line.strip()]
            
            page_content = PageContent(
                page_number=page_num,
                text=text,
                lines=clean_lines,
                word_count=len(text.split()),
                char_count=len(text)
            )
            page_contents.append(page_content)
            
            # Her satırı kaynak bilgisiyle kaydet
            for line_idx, line_text in enumerate(clean_lines):
                all_lines.append(TextLine(
                    text=line_text,
                    page_number=page_num,
                    line_in_page=line_idx + 1
                ))
        
        return page_contents, all_lines
    
    def extract_with_pdfplumber(self, file_path: str) -> PDFDocument:
        if not HAS_PDFPLUMBER:
            raise ImportError("pdfplumber yüklü değil. pip install pdfplumber")
        
        pages_data = []
        metadata = {}
        
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                
                with pdfplumber.open(file_path) as pdf:
                    metadata = pdf.metadata or {}
                    total_pages = len(pdf.pages)
                    
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        pages_data.append((i + 1, text))
                    
        except Exception as e:
            raise Exception(f"PDF okuma hatası (pdfplumber): {str(e)}")
        
        page_contents, all_lines = self._process_pages(pages_data)
        
        return PDFDocument(
            file_path=file_path,
            total_pages=total_pages,
            pages=page_contents,
            metadata=metadata,
            all_lines=all_lines
        )
    
    def extract_with_pypdf2(self, file_path: str) -> PDFDocument:
        if not HAS_PYPDF2:
            raise ImportError("PyPDF2 yüklü değil. pip install PyPDF2")
        
        pages_data = []
        metadata = {}
        
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                
                reader = PdfReader(file_path)
                metadata = dict(reader.metadata) if reader.metadata else {}
                total_pages = len(reader.pages)
                
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages_data.append((i + 1, text))
                
        except Exception as e:
            raise Exception(f"PDF okuma hatası (PyPDF2): {str(e)}")
        
        page_contents, all_lines = self._process_pages(pages_data)
        
        return PDFDocument(
            file_path=file_path,
            total_pages=total_pages,
            pages=page_contents,
            metadata=metadata,
            all_lines=all_lines
        )
    
    def extract(self, file_path: str, method: str = "auto") -> PDFDocument:
        if method == "auto":
            if HAS_PDFPLUMBER:
                try:
                    return self.extract_with_pdfplumber(file_path)
                except:
                    pass
            if HAS_PYPDF2:
                return self.extract_with_pypdf2(file_path)
            raise ImportError("PDF okuyucu bulunamadı. pip install pdfplumber PyPDF2")
        elif method == "pdfplumber":
            return self.extract_with_pdfplumber(file_path)
        else:
            return self.extract_with_pypdf2(file_path)


class TextPreprocessor:
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()
    
    @staticmethod
    def remove_page_numbers(text: str) -> str:
        patterns = [
            r'^\d+\s*$',
            r'^Page\s+\d+',
            r'^Sayfa\s+\d+',
            r'^\d+\s*/\s*\d+$',
            r'^-\s*\d+\s*-$',
        ]
        line = text.strip()
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return ""
        return text
    
    @staticmethod
    def clean_text(text: str, options: Dict = None) -> str:
        if options is None:
            options = {}
        
        if options.get('normalize_whitespace', True):
            text = re.sub(r' +', ' ', text).strip()
        
        if options.get('remove_page_numbers', False):
            text = TextPreprocessor.remove_page_numbers(text)
        
        if options.get('lowercase', False):
            text = text.lower()
        
        return text
    
    @staticmethod
    def clean_lines(lines: List['TextLine'], options: Dict = None) -> List['TextLine']:
        if options is None:
            options = {}
        
        result = []
        for line in lines:
            cleaned_text = TextPreprocessor.clean_text(line.text, options)
            if cleaned_text:  # Skip empty rows
                result.append(TextLine(
                    text=cleaned_text,
                    page_number=line.page_number,
                    line_in_page=line.line_in_page
                ))
        return result