from typing import List, Union
import html
from datetime import datetime
import sys
import os
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from .utils.helpers import DiffType, WordDiff, LineDiff
from .text_comparator import ComparisonResult


class HTMLReportGenerator:    
    CSS_STYLES = """
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; padding: 20px; background: #f5f5f5; 
        }
        .container { max-width: 1600px; margin: 0 auto; }
        .header { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 { margin: 0 0 10px 0; }
        .header p { margin: 5px 0; opacity: 0.9; }
        
        .summary { 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); 
            gap: 15px; margin-bottom: 20px; 
        }
        .summary-card { 
            background: white; padding: 15px; border-radius: 10px; text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-card .value { font-size: 1.8em; font-weight: bold; color: #667eea; }
        .summary-card .label { color: #666; margin-top: 5px; font-size: 0.85em; }
        .summary-card.additions .value { color: #2e7d32; }
        .summary-card.deletions .value { color: #c62828; }
        .summary-card.modifications .value { color: #f57c00; }
        
        .comparison-section { 
            background: white; border-radius: 10px; overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px;
        }
        .section-header { 
            background: #f0f0f0; padding: 12px 20px; border-bottom: 1px solid #ddd;
            display: flex; justify-content: space-between; align-items: center;
        }
        .section-header h3 { margin: 0; color: #333; font-size: 1em; }
        .similarity-badge { 
            background: #667eea; color: white; padding: 4px 12px; 
            border-radius: 15px; font-size: 0.85em;
        }
        
        .diff-table { 
            width: 100%; 
            border-collapse: collapse; 
            table-layout: fixed;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
        }
        .diff-table th {
            background: #fafafa;
            padding: 10px 15px;
            text-align: left;
            font-weight: bold;
            border-bottom: 2px solid #e0e0e0;
            position: sticky;
            top: 0;
        }
        .diff-table td { 
            padding: 4px 8px;
            vertical-align: top;
            border-bottom: 1px solid #f0f0f0;
        }
        .diff-table .line-num {
            width: 50px;
            text-align: right;
            color: #999;
            background: #fafafa;
            border-right: 1px solid #e0e0e0;
            font-size: 0.85em;
            user-select: none;
        }
        .diff-table .line-content {
            white-space: pre-wrap;
            word-break: break-word;
            padding-left: 12px;
        }
        .diff-table .page-info {
            width: 40px;
            text-align: center;
            color: #999;
            font-size: 0.8em;
            background: #fafafa;
        }
        
        .diff-table tr.equal td { background: white; }
        .diff-table tr.insert td.new-side { background: #e8f5e9; }
        .diff-table tr.insert td.old-side { background: #fafafa; }
        .diff-table tr.delete td.old-side { background: #ffebee; }
        .diff-table tr.delete td.new-side { background: #fafafa; }
        .diff-table tr.replace td.old-side { background: #fff8e1; }
        .diff-table tr.replace td.new-side { background: #fff8e1; }
        
        .word-insert { 
            background: #81c784; 
            padding: 1px 4px; 
            border-radius: 3px; 
            color: #1b5e20;
        }
        .word-delete { 
            background: #e57373; 
            padding: 1px 4px; 
            border-radius: 3px;
            text-decoration: line-through; 
            color: #b71c1c;
        }
        
        .legend { 
            display: flex; gap: 25px; padding: 12px 20px; background: #fafafa; 
            border-top: 1px solid #e0e0e0; flex-wrap: wrap;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.9em; }
        .legend-color { width: 18px; height: 18px; border-radius: 4px; }
        .legend-color.insert { background: #a5d6a7; }
        .legend-color.delete { background: #ef9a9a; }
        .legend-color.replace { background: #fff59d; }
        
        .footer { text-align: center; padding: 20px; color: #666; font-size: 0.9em; }
        
        .toc { background: white; padding: 15px 20px; border-radius: 10px; margin-bottom: 20px; }
        .toc h3 { margin: 0 0 10px 0; font-size: 1em; }
        .toc ul { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 10px; }
        .toc li a { 
            display: block; padding: 5px 12px; background: #f0f0f0; border-radius: 5px;
            color: #667eea; text-decoration: none; font-size: 0.9em;
        }
        .toc li a:hover { background: #e0e0e0; }
    </style>
    """
    
    @staticmethod
    def escape(text: str) -> str:
        return html.escape(text) if text else ""
    
    def format_word_diffs_old(self, word_diffs: List[WordDiff]) -> str:
        parts = []
        for wd in word_diffs:
            escaped = self.escape(wd.word)
            if wd.diff_type == DiffType.EQUAL:
                parts.append(escaped)
            elif wd.diff_type == DiffType.DELETE:
                parts.append(f'<span class="word-delete">{escaped}</span>')
        return ' '.join(parts)
    
    def format_word_diffs_new(self, word_diffs: List[WordDiff]) -> str:
        parts = []
        for wd in word_diffs:
            escaped = self.escape(wd.word)
            if wd.diff_type == DiffType.EQUAL:
                parts.append(escaped)
            elif wd.diff_type == DiffType.INSERT:
                parts.append(f'<span class="word-insert">{escaped}</span>')
        return ' '.join(parts)
    
    def generate_diff_row(self, line_diff: LineDiff) -> str:
        diff_type = line_diff.diff_type.value
        
        old_num = line_diff.line_number_old if line_diff.line_number_old else ""
        old_page = f"P{line_diff.old_page}" if line_diff.old_page else ""
        
        new_num = line_diff.line_number_new if line_diff.line_number_new else ""
        new_page = f"P{line_diff.new_page}" if line_diff.new_page else ""
        
        if line_diff.diff_type == DiffType.EQUAL:
            old_content = self.escape(line_diff.old_line)
            new_content = self.escape(line_diff.new_line)
        elif line_diff.diff_type == DiffType.INSERT:
            old_content = ""
            if line_diff.word_diffs:
                new_content = self.format_word_diffs_new(line_diff.word_diffs)
            else:
                new_content = f'<span class="word-insert">{self.escape(line_diff.new_line)}</span>'
        elif line_diff.diff_type == DiffType.DELETE:
            if line_diff.word_diffs:
                old_content = self.format_word_diffs_old(line_diff.word_diffs)
            else:
                old_content = f'<span class="word-delete">{self.escape(line_diff.old_line)}</span>'
            new_content = ""
        else:  # REPLACE
            if line_diff.word_diffs:
                old_content = self.format_word_diffs_old(line_diff.word_diffs)
                new_content = self.format_word_diffs_new(line_diff.word_diffs)
            else:
                old_content = f'<span class="word-delete">{self.escape(line_diff.old_line)}</span>'
                new_content = f'<span class="word-insert">{self.escape(line_diff.new_line)}</span>'
        
        return f'''
        <tr class="{diff_type}">
            <td class="line-num old-side">{old_num}</td>
            <td class="line-content old-side">{old_content}</td>
            <td class="line-num new-side">{new_num}</td>
            <td class="line-content new-side">{new_content}</td>
        </tr>
        '''
    
    def generate_group_html(self, group: dict, group_index: int) -> str:
        page_num = group.get('page_number', group_index + 1)
        similarity = group.get('similarity', 0)
        line_diffs = group.get('line_diffs', [])
        
        rows_html = ""
        for line_diff in line_diffs:
            rows_html += self.generate_diff_row(line_diff)
        
        additions = sum(1 for ld in line_diffs if ld.diff_type == DiffType.INSERT)
        deletions = sum(1 for ld in line_diffs if ld.diff_type == DiffType.DELETE)
        modifications = sum(1 for ld in line_diffs if ld.diff_type == DiffType.REPLACE)
        
        stats_parts = []
        if additions > 0:
            stats_parts.append(f'<span style="color:#2e7d32">+{additions}</span>')
        if deletions > 0:
            stats_parts.append(f'<span style="color:#c62828">-{deletions}</span>')
        if modifications > 0:
            stats_parts.append(f'<span style="color:#f57c00">~{modifications}</span>')
        
        stats_str = " &nbsp;|&nbsp; ".join(stats_parts) if stats_parts else "✓ No changes"
        
        return f'''
        <div class="comparison-section" id="section-{group_index}">
            <div class="section-header">
                <h3>📄 Section {group_index + 1} (Page ~{page_num})</h3>
                <div>
                    {stats_str} &nbsp;|&nbsp;
                    <span class="similarity-badge">{similarity:.0%} similarity</span>
                </div>
            </div>
            <table class="diff-table">
                <thead>
                    <tr>
                        <th class="line-num">Line</th>
                        <th>Original File</th>
                        <th class="line-num">Line</th>
                        <th>New File</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        '''
    
    def generate_report(self, result: ComparisonResult) -> str:
        summary = result.summary
        doc_diff = result.document_diff
        
        page_groups = doc_diff.page_groups if doc_diff.page_groups else []
        
        if not page_groups and doc_diff.line_diffs:
            page_groups = [{
                'page_number': 1,
                'line_diffs': doc_diff.line_diffs,
                'similarity': doc_diff.overall_similarity
            }]
        
        toc_items = ""
        for i, group in enumerate(page_groups):
            page_num = group.get('page_number', i + 1)
            toc_items += f'<li><a href="#section-{i}">Section {i + 1} (S.{page_num})</a></li>'
        
        toc_html = f'''
        <div class="toc">
            <h3>📑 Sections</h3>
            <ul>{toc_items}</ul>
        </div>
        ''' if len(page_groups) > 1 else ""
        
        sections_html = ""
        for i, group in enumerate(page_groups):
            sections_html += self.generate_group_html(group, i)
        
        file1_name = "first.pdf" #os.path.basename(summary.get('file1', 'Dosya 1'))
        file2_name = "second.pdf" #os.path.basename(summary.get('file2', 'Dosya 2'))
        
        report = f'''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>PDF Comparison Report</title>
            {self.CSS_STYLES}
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>PDF Comparison Report</h1>
                    <p>📄 <strong>{self.escape(file1_name)}</strong> ↔ <strong>{self.escape(file2_name)}</strong></p>
                    <p>📅 {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}</p>
                </div>
                
                <div class="summary">
                    <div class="summary-card">
                        <div class="value">{summary['similarity']}</div>
                        <div class="label">Similarity</div>
                    </div>
                    <div class="summary-card additions">
                        <div class="value">+{summary['additions']}</div>
                        <div class="label">Added</div>
                    </div>
                    <div class="summary-card deletions">
                        <div class="value">-{summary['deletions']}</div>
                        <div class="label">Deleted</div>
                    </div>
                    <div class="summary-card modifications">
                        <div class="value">~{summary['modifications']}</div>
                        <div class="label">Changed</div>
                    </div>
                    <div class="summary-card">
                        <div class="value">{summary['total_pages_1']}/{summary['total_pages_2']}</div>
                        <div class="label">Page</div>
                    </div>
                    <div class="summary-card">
                        <div class="value">{summary.get('total_lines_1', 0)}/{summary.get('total_lines_2', 0)}</div>
                        <div class="label">Line</div>
                    </div>
                </div>
                
                <div class="comparison-section">
                    <div class="legend">
                        <div class="legend-item">
                            <div class="legend-color insert"></div>
                            <span>Added</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color delete"></div>
                            <span>Deleted</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color replace"></div>
                            <span>Changed</span>
                        </div>
                    </div>
                </div>
                
                {toc_html}
                
                {sections_html}
                
                <div class="footer">
                    <p>AW Center © 2025 | Total {summary['total_changes']} changes</p>
                </div>
            </div>
        </body>
        </html>
        '''
        
        return report
    
    def save_report(self, result: ComparisonResult, output_path: Union[str, BytesIO]):
        html_content = self.generate_report(result)
        if isinstance(output_path, str):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        elif isinstance(output_path, BytesIO):
            output_path.write(html_content.encode('utf-8'))
            output_path.seek(0)
        else:
            raise TypeError("output_path must be a str or BytesIO object")