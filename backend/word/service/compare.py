"""Document comparison helpers for Word workflows."""

import re
import unicodedata
from difflib import SequenceMatcher

import docx2txt


def u_normalize(s: str) -> str:
    """Normalize whitespace and invisible characters for comparison."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u00A0", " ")
    s = s.replace("\u200B", "")
    s = s.replace("\r", "")
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def split_sentences(text: str):
    """Split text into packed sentence groups using legacy punctuation rules."""
    if not text:
        return []
    parts = re.split(r'(?<=[\.\!\?\:\;])\s+', text) if text else []
    packed, buf = [], []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        buf.append(p)
        if len(" ".join(buf)) > 80:
            packed.append(" ".join(buf))
            buf = []
    if buf:
        packed.append(" ".join(buf))
    return packed if packed else [text]

def tokenize_words(s: str):
    """Tokenize words and punctuation for redline diffing."""
    return re.findall(r"\w+|[^\w\s]", s, flags=re.UNICODE)

def ratio(a: str, b: str) -> float:
    """Return SequenceMatcher similarity with autojunk disabled."""
    return SequenceMatcher(None, a, b, autojunk=False).ratio()

# Read

def read_docx_lines_with_index(path: str):
    """Read non-empty normalized DOCX text lines with original indexes."""
    raw = docx2txt.process(path)
    lines = [u_normalize(ln) for ln in raw.splitlines()]
    out = []
    for idx, ln in enumerate(lines):
        if ln.strip():
            out.append((idx, ln))  # (index, text)
    return out

# Auto Ratio

def auto_thresholds(lines1, lines2):
    """Calculate legacy automatic equal and weak-equal thresholds."""
    if not lines1 and not lines2:
        return 0.92, 0.86

    all_txt = [t for _, t in lines1] + [t for _, t in lines2]
    avg_len = sum(len(x) for x in all_txt) / max(1, len(all_txt))
    n1, n2 = len(lines1), len(lines2)

    sample_pairs = []
    window = 3
    for i, a in lines1[::max(1, max(n1,1)//200 + 1)]:
        for off in range(-window, window+1):
            jpos = i + off
            if 0 <= jpos < n2:
                b = lines2[jpos][1]
                sample_pairs.append(ratio(a, b))
    if not sample_pairs:
        sample_pairs = [0.0]

    p90 = sorted(sample_pairs)[int(0.9 * (len(sample_pairs)-1))]
    if avg_len <= 40:
        base_equal = 0.90
    elif avg_len >= 140:
        base_equal = 0.95
    else:
        base_equal = 0.90 + (avg_len - 40) * (0.95 - 0.90) / 100.0

    equal_ratio = max(0.88, min(0.98, (base_equal + p90) / 2))
    weak_equal_ratio = max(0.82, equal_ratio - 0.06)

    return equal_ratio, weak_equal_ratio

# Paragraph

def align_paragraphs_indexed(lines1, lines2, equal_ratio=0.92, weak_equal_ratio=0.86):
    """Align indexed paragraph lines and tag equal, insert, delete, replace rows."""
    sequence_matcher = SequenceMatcher(None, text_values(lines1), text_values(lines2), autojunk=False)
    aligned_rows = []
    for tag, first_start, first_end, second_start, second_end in sequence_matcher.get_opcodes():
        aligned_rows.extend(
            align_opcode(
                tag,
                lines1[first_start:first_end],
                lines2[second_start:second_end],
                equal_ratio,
                weak_equal_ratio,
            )
        )
    return aligned_rows


def text_values(lines):
    """Return only text values from indexed line tuples."""
    return [text for _, text in lines]


def align_opcode(tag, first_block, second_block, equal_ratio, weak_equal_ratio):
    """Align a SequenceMatcher opcode block using the legacy row shape."""
    if tag == "equal":
        return equal_rows(first_block, second_block)
    if tag == "delete":
        return deleted_rows(first_block)
    if tag == "insert":
        return inserted_rows(second_block)
    if tag == "replace":
        return replaced_rows(first_block, second_block, equal_ratio, weak_equal_ratio)
    return []


def equal_rows(first_block, second_block):
    """Return aligned equal rows for matching paragraph blocks."""
    return [(ai, at, bj, bt, "equal") for (ai, at), (bj, bt) in zip(first_block, second_block)]


def deleted_rows(first_block):
    """Return deleted rows for first-document paragraph blocks."""
    return [(index, text, None, None, "delete") for index, text in first_block]


def inserted_rows(second_block):
    """Return inserted rows for second-document paragraph blocks."""
    return [(None, None, index, text, "insert") for index, text in second_block]


def replaced_rows(first_block, second_block, equal_ratio, weak_equal_ratio):
    """Return best-match replace rows plus unmatched insert rows."""
    used_second_indexes = set()
    output_rows = []
    for first_index, first_text in first_block:
        output_rows.append(
            match_replacement(
                first_index, first_text, second_block, used_second_indexes, equal_ratio, weak_equal_ratio
            )
        )
    output_rows.extend(unmatched_insert_rows(second_block, used_second_indexes))
    return output_rows


def match_replacement(first_index, first_text, second_block, used_second_indexes, equal_ratio, weak_equal_ratio):
    """Return the legacy row for one replaced paragraph candidate."""
    best_index, best_ratio = find_best_match(first_text, second_block, used_second_indexes)
    if best_index == -1:
        return first_index, first_text, None, None, "delete"
    second_index, second_text = second_block[best_index]
    used_second_indexes.add(best_index)
    return (
        first_index,
        first_text,
        second_index,
        second_text,
        classify_match(best_ratio, equal_ratio, weak_equal_ratio),
    )


def find_best_match(first_text, second_block, used_second_indexes):
    """Find the unused second-block row with the highest similarity."""
    best_index, best_ratio = -1, 0.0
    for index, (_, second_text) in enumerate(second_block):
        if index in used_second_indexes:
            continue
        current_ratio = ratio(first_text, second_text)
        if current_ratio > best_ratio:
            best_index, best_ratio = index, current_ratio
    return best_index, best_ratio


def classify_match(match_ratio, equal_ratio, weak_equal_ratio):
    """Classify a replacement match with the legacy threshold rules."""
    if match_ratio >= equal_ratio:
        return "equal"
    if match_ratio >= weak_equal_ratio:
        return "replace"
    return "delete"


def unmatched_insert_rows(second_block, used_second_indexes):
    """Return insert rows for second-block paragraphs that were not matched."""
    return [
        (None, None, second_index, second_text, "insert")
        for index, (second_index, second_text) in enumerate(second_block)
        if index not in used_second_indexes
    ]
