from difflib import SequenceMatcher
from typing import List, Dict, Optional
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from .utils.helpers import (
    DiffType, WordDiff, LineDiff, DocumentDiff,
    split_into_words, calculate_similarity, normalize_text
)
from .pdf_extractor import TextLine


class DiffEngine:
    def __init__(self, ignore_whitespace: bool = True, ignore_case: bool = False):
        self.ignore_whitespace = ignore_whitespace
        self.ignore_case = ignore_case
    
    def preprocess(self, text: str) -> str:
        if self.ignore_whitespace:
            text = normalize_text(text)
        if self.ignore_case:
            text = text.lower()
        return text
    
    def normalize_for_comparison(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def compare_words(self, text1: str, text2: str) -> List[WordDiff]:
        norm_text1 = self.normalize_for_comparison(text1)
        norm_text2 = self.normalize_for_comparison(text2)
        
        words1 = split_into_words(self.preprocess(norm_text1))
        words2 = split_into_words(self.preprocess(norm_text2))
        
        orig_words1 = split_into_words(norm_text1)
        orig_words2 = split_into_words(norm_text2)
        
        matcher = SequenceMatcher(None, words1, words2)
        result = []
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1):
                    idx = i1 + k
                    word = orig_words1[idx] if idx < len(orig_words1) else words1[idx]
                    result.append(WordDiff(word=word, diff_type=DiffType.EQUAL))
                    
            elif tag == 'insert':
                for k in range(j2 - j1):
                    idx = j1 + k
                    word = orig_words2[idx] if idx < len(orig_words2) else words2[idx]
                    result.append(WordDiff(word=word, diff_type=DiffType.INSERT))
                    
            elif tag == 'delete':
                for k in range(i2 - i1):
                    idx = i1 + k
                    word = orig_words1[idx] if idx < len(orig_words1) else words1[idx]
                    result.append(WordDiff(word=word, diff_type=DiffType.DELETE))
                    
            elif tag == 'replace':
                for k in range(i2 - i1):
                    idx = i1 + k
                    word = orig_words1[idx] if idx < len(orig_words1) else words1[idx]
                    result.append(WordDiff(word=word, diff_type=DiffType.DELETE))
                for k in range(j2 - j1):
                    idx = j1 + k
                    word = orig_words2[idx] if idx < len(orig_words2) else words2[idx]
                    result.append(WordDiff(word=word, diff_type=DiffType.INSERT))
        
        return result
    
    def are_lines_similar(self, line1: str, line2: str, threshold: float = 0.85) -> bool:
        norm1 = self.preprocess(line1)
        norm2 = self.preprocess(line2)
        
        if not norm1 and not norm2:
            return True
        if not norm1 or not norm2:
            return False
        
        ratio = SequenceMatcher(None, norm1, norm2).ratio()
        return ratio >= threshold
    
    def compare_full_text(self, lines1: List[TextLine], lines2: List[TextLine]) -> DocumentDiff:
        texts1 = [self.normalize_for_comparison(line.text) for line in lines1]
        texts2 = [self.normalize_for_comparison(line.text) for line in lines2]
        
        processed1 = [self.preprocess(t) for t in texts1]
        processed2 = [self.preprocess(t) for t in texts2]
        
        matcher = SequenceMatcher(None, processed1, processed2)
        
        line_diffs = []
        total_additions = 0
        total_deletions = 0
        total_modifications = 0
        
        line_num_old = 0
        line_num_new = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1):
                    old_idx = i1 + k
                    new_idx = j1 + k
                    line_num_old += 1
                    line_num_new += 1
                    
                    old_line = lines1[old_idx]
                    new_line = lines2[new_idx]
                    
                    line_diffs.append(LineDiff(
                        line_number_old=line_num_old,
                        line_number_new=line_num_new,
                        diff_type=DiffType.EQUAL,
                        old_line=texts1[old_idx],
                        new_line=texts2[new_idx],
                        word_diffs=[],
                        old_page=old_line.page_number,
                        new_page=new_line.page_number
                    ))
                    
            elif tag == 'insert':
                for k in range(j2 - j1):
                    new_idx = j1 + k
                    line_num_new += 1
                    
                    new_line = lines2[new_idx]
                    word_diffs = [WordDiff(word=w, diff_type=DiffType.INSERT) 
                                  for w in split_into_words(texts2[new_idx])]
                    
                    line_diffs.append(LineDiff(
                        line_number_old=0,
                        line_number_new=line_num_new,
                        diff_type=DiffType.INSERT,
                        old_line="",
                        new_line=texts2[new_idx],
                        word_diffs=word_diffs,
                        old_page=0,
                        new_page=new_line.page_number
                    ))
                    total_additions += 1
                    
            elif tag == 'delete':
                for k in range(i2 - i1):
                    old_idx = i1 + k
                    line_num_old += 1
                    
                    old_line = lines1[old_idx]
                    word_diffs = [WordDiff(word=w, diff_type=DiffType.DELETE) 
                                  for w in split_into_words(texts1[old_idx])]
                    
                    line_diffs.append(LineDiff(
                        line_number_old=line_num_old,
                        line_number_new=0,
                        diff_type=DiffType.DELETE,
                        old_line=texts1[old_idx],
                        new_line="",
                        word_diffs=word_diffs,
                        old_page=old_line.page_number,
                        new_page=0
                    ))
                    total_deletions += 1
                    
            elif tag == 'replace':
                old_count = i2 - i1
                new_count = j2 - j1
                max_count = max(old_count, new_count)
                
                for k in range(max_count):
                    old_idx = i1 + k if k < old_count else None
                    new_idx = j1 + k if k < new_count else None
                    
                    old_line = lines1[old_idx] if old_idx is not None else None
                    new_line = lines2[new_idx] if new_idx is not None else None
                    
                    old_text = texts1[old_idx] if old_idx is not None else ""
                    new_text = texts2[new_idx] if new_idx is not None else ""
                    
                    if old_line:
                        line_num_old += 1
                    if new_line:
                        line_num_new += 1
                    
                    if old_line and new_line:
                        word_diffs = self.compare_words(old_text, new_text)
                        diff_type = DiffType.REPLACE
                        total_modifications += 1
                    elif old_line:
                        word_diffs = [WordDiff(word=w, diff_type=DiffType.DELETE) 
                                      for w in split_into_words(old_text)]
                        diff_type = DiffType.DELETE
                        total_deletions += 1
                    else:
                        word_diffs = [WordDiff(word=w, diff_type=DiffType.INSERT) 
                                      for w in split_into_words(new_text)]
                        diff_type = DiffType.INSERT
                        total_additions += 1
                    
                    line_diffs.append(LineDiff(
                        line_number_old=line_num_old if old_line else 0,
                        line_number_new=line_num_new if new_line else 0,
                        diff_type=diff_type,
                        old_line=old_text,
                        new_line=new_text,
                        word_diffs=word_diffs,
                        old_page=old_line.page_number if old_line else 0,
                        new_page=new_line.page_number if new_line else 0
                    ))
        
        all_text1 = '\n'.join(texts1)
        all_text2 = '\n'.join(texts2)
        overall_similarity = calculate_similarity(
            self.preprocess(all_text1), 
            self.preprocess(all_text2)
        )
        
        page_groups = self._create_page_groups(line_diffs, lines1, lines2)
        
        return DocumentDiff(
            line_diffs=line_diffs,
            overall_similarity=overall_similarity,
            total_additions=total_additions,
            total_deletions=total_deletions,
            total_modifications=total_modifications,
            total_lines_old=len(lines1),
            total_lines_new=len(lines2),
            page_groups=page_groups
        )
    
    def _create_page_groups(self, line_diffs: List[LineDiff], 
                            lines1: List[TextLine], lines2: List[TextLine]) -> List[dict]:
        if not line_diffs:
            return []
        
        groups = []
        current_group = []
        current_page = None
        
        for ld in line_diffs:
            # Determine the active page number
            page = ld.old_page or ld.new_page or 1
            
            if current_page is None:
                current_page = page
            
            # Did the page change
            if page != current_page and current_group:
                equal_count = sum(1 for l in current_group if l.diff_type == DiffType.EQUAL)
                similarity = equal_count / len(current_group) if current_group else 1.0
                
                groups.append({
                    'page_number': current_page,
                    'line_diffs': current_group,
                    'similarity': similarity
                })
                current_group = []
                current_page = page
            
            current_group.append(ld)
        
        # Add the last group
        if current_group:
            equal_count = sum(1 for l in current_group if l.diff_type == DiffType.EQUAL)
            similarity = equal_count / len(current_group) if current_group else 1.0
            
            groups.append({
                'page_number': current_page,
                'line_diffs': current_group,
                'similarity': similarity
            })
        
        return groups