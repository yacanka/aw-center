from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from .pdf_extractor import PDFExtractor, PDFDocument, TextPreprocessor, TextLine
from .diff_engine import DiffEngine, DocumentDiff
from .utils.helpers import ComparisonMode


@dataclass
class ComparisonOptions:
    ignore_whitespace: bool = True
    ignore_case: bool = False
    ignore_page_numbers: bool = True
    extraction_method: str = "auto"
    mode: ComparisonMode = ComparisonMode.FULL_TEXT


@dataclass
class ComparisonResult:
    doc1: PDFDocument
    doc2: PDFDocument
    document_diff: DocumentDiff
    options: ComparisonOptions
    
    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "file1": self.doc1.file_path,
            "file2": self.doc2.file_path,
            "similarity": f"{self.document_diff.overall_similarity:.1%}",
            "total_pages_1": self.doc1.total_pages,
            "total_pages_2": self.doc2.total_pages,
            "total_lines_1": self.document_diff.total_lines_old,
            "total_lines_2": self.document_diff.total_lines_new,
            "additions": self.document_diff.total_additions,
            "deletions": self.document_diff.total_deletions,
            "modifications": self.document_diff.total_modifications,
            "total_changes": (
                self.document_diff.total_additions + 
                self.document_diff.total_deletions + 
                self.document_diff.total_modifications
            )
        }
    
    @property
    def page_groups(self) -> List[dict]:
        return self.document_diff.page_groups


class PDFComparator:
    def __init__(self, options: ComparisonOptions = None):
        self.options = options or ComparisonOptions()
        self.extractor = PDFExtractor()
        self.diff_engine = DiffEngine(
            ignore_whitespace=self.options.ignore_whitespace,
            ignore_case=self.options.ignore_case
        )
        self.preprocessor = TextPreprocessor()
    
    def load_pdf(self, file_path: str) -> PDFDocument:
        return self.extractor.extract(file_path, self.options.extraction_method)
    
    def preprocess_lines(self, lines: List[TextLine]) -> List[TextLine]:
        preprocess_options = {
            'normalize_whitespace': self.options.ignore_whitespace,
            'remove_page_numbers': self.options.ignore_page_numbers,
            'lowercase': self.options.ignore_case
        }
        return self.preprocessor.clean_lines(lines, preprocess_options)
    
    def compare(self, file1: str, file2: str) -> ComparisonResult:
        doc1 = self.load_pdf(file1)
        doc2 = self.load_pdf(file2)
        
        lines1 = self.preprocess_lines(doc1.all_lines)
        lines2 = self.preprocess_lines(doc2.all_lines)
        
        document_diff = self.diff_engine.compare_full_text(lines1, lines2)
        
        return ComparisonResult(
            doc1=doc1,
            doc2=doc2,
            document_diff=document_diff,
            options=self.options
        )
    
    def compare_text(self, text1: str, text2: str) -> DocumentDiff:
        lines1 = [
            TextLine(text=line.strip(), page_number=1, line_in_page=i+1)
            for i, line in enumerate(text1.split('\n')) 
            if line.strip()
        ]
        lines2 = [
            TextLine(text=line.strip(), page_number=1, line_in_page=i+1)
            for i, line in enumerate(text2.split('\n')) 
            if line.strip()
        ]
        
        return self.diff_engine.compare_full_text(lines1, lines2)