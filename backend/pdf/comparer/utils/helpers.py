import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class DiffType(Enum):
    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"


class ComparisonMode(Enum):
    FULL_TEXT = "full_text"       # Compare all text
    PAGE_BY_PAGE = "page_by_page"  # Compare page by page


@dataclass
class DiffResult:
    diff_type: DiffType
    old_text: str = ""
    new_text: str = ""
    old_position: Tuple[int, int] = (0, 0)
    new_position: Tuple[int, int] = (0, 0)


@dataclass
class WordDiff:
    word: str
    diff_type: DiffType
    

@dataclass
class TextLine:
    text: str
    page_number: int
    line_in_page: int  # Number of line in page


@dataclass
class LineDiff:
    line_number_old: int
    line_number_new: int
    diff_type: DiffType
    old_line: str = ""
    new_line: str = ""
    word_diffs: List[WordDiff] = field(default_factory=list)
    old_page: int = 0
    new_page: int = 0


@dataclass
class PageDiff:
    page_number: int
    line_diffs: List[LineDiff]
    similarity_ratio: float


@dataclass 
class DocumentDiff:
    line_diffs: List[LineDiff]  # All line diffs
    overall_similarity: float
    total_additions: int
    total_deletions: int
    total_modifications: int
    total_lines_old: int
    total_lines_new: int
    page_groups: List[dict] = field(default_factory=list)


def normalize_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def split_into_words(text: str) -> List[str]:
    pattern = r'(\S+)'
    words = re.findall(pattern, text)
    return words


def split_into_sentences(text: str) -> List[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def calculate_similarity(text1: str, text2: str) -> float:
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, text1, text2).ratio()


def get_color_for_diff_type(diff_type: DiffType) -> Tuple[str, str]:
    colors = {
        DiffType.EQUAL: ("#FFFFFF", "#000000"),
        DiffType.INSERT: ("#C8E6C9", "#1B5E20"),
        DiffType.DELETE: ("#FFCDD2", "#B71C1C"),
        DiffType.REPLACE: ("#FFF9C4", "#F57F17"),
    }
    return colors.get(diff_type, ("#FFFFFF", "#000000"))