from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django import forms
from django.core.cache import cache

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView 
from rest_framework import status

import pandas as pd
import json
from io import BytesIO

import re
import unicodedata
import docx2txt
import pandas as pd
from difflib import SequenceMatcher
from docx import Document
from docx.shared import Pt
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.formatting.rule import CellIsRule, FormulaRule, ColorScaleRule, DataBarRule
from openpyxl.utils import get_column_letter
from docx.enum.text import WD_COLOR_INDEX

from pathlib import Path
import sys
import time
import uuid
from base64 import b64decode, b64encode

from word.service.translator import get_text_generator

# Utils

class UploadForm(forms.Form):
    file = forms.FileField()

def u_normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u00A0", " ")
    s = s.replace("\u200B", "")
    s = s.replace("\r", "")
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def split_sentences(text: str):
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
            packed.append(" ".join(buf)); buf = []
    if buf:
        packed.append(" ".join(buf))
    return packed if packed else [text]

def tokenize_words(s: str):
    return re.findall(r"\w+|[^\w\s]", s, flags=re.UNICODE)

def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()

# Read

def read_docx_lines_with_index(path: str):
    raw = docx2txt.process(path)
    lines = [u_normalize(ln) for ln in raw.splitlines()]
    out = []
    for idx, ln in enumerate(lines):
        if ln.strip():
            out.append((idx, ln))  # (index, text)
    return out

# Auto Ratio

def auto_thresholds(lines1, lines2):
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
    s1 = [t for _, t in lines1]
    s2 = [t for _, t in lines2]
    sm = SequenceMatcher(None, s1, s2, autojunk=False)
    out = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                ai, at = lines1[i1 + k]
                bj, bt = lines2[j1 + k]
                out.append((ai, at, bj, bt, 'equal'))
        elif tag == "delete":
            for k in range(i2 - i1):
                ai, at = lines1[i1 + k]
                out.append((ai, at, None, None, 'delete'))
        elif tag == "insert":
            for k in range(j2 - j1):
                bj, bt = lines2[j1 + k]
                out.append((None, None, bj, bt, 'insert'))
        elif tag == "replace":
            block1 = lines1[i1:i2]
            block2 = lines2[j1:j2]
            used2 = set()

            for ai, at in block1:
                best = (-1, 0.0)
                for idx, (bj, bt) in enumerate(block2):
                    if idx in used2:
                        continue
                    r = ratio(at, bt)
                    if r > best[1]:
                        best = (idx, r)
                if best[0] != -1:
                    bj, bt = block2[best[0]]
                    if best[1] >= equal_ratio:
                        out.append((ai, at, bj, bt, 'equal'))
                    elif best[1] >= weak_equal_ratio:
                        out.append((ai, at, bj, bt, 'replace'))
                    else:
                        out.append((ai, at, None, None, 'delete'))
                    used2.add(best[0])
                else:
                    out.append((ai, at, None, None, 'delete'))

            for idx, (bj, bt) in enumerate(block2):
                if idx not in used2:
                    out.append((None, None, bj, bt, 'insert'))

    return out

# DOCX redline style

def style_added(run):
    run.font.underline = True
    run.font.color.rgb = None
    run.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN  # optional

def style_deleted(run):
    run.font.strike = True
    run.font.color.rgb = None
    run.font.highlight_color = WD_COLOR_INDEX.RED  # optional

def style_normal(run):
    run.font.strike = False
    run.font.underline = False

def add_legend(doc: Document):
    p = doc.add_paragraph()
    r = p.add_run("Legend: ")
    r.bold = True
    r.font.size = Pt(11)
    p = doc.add_paragraph()
    r = p.add_run("Added"); style_added(r)
    p.add_run("  |  ")
    r2 = p.add_run("Deleted"); style_deleted(r2)
    p.add_run("  |  Changes are shown first as Deleted, then as Added.")

def write_word_diff(par, a_text: str, b_text: str):
    a_tokens = tokenize_words(a_text or "")
    b_tokens = tokenize_words(b_text or "")
    sm = SequenceMatcher(None, a_tokens, b_tokens, autojunk=False)
    first = True
    def add(tok, styler):
        nonlocal first
        if not first:
            par.add_run(" ")
        r = par.add_run(tok)
        styler(r)
        first = False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for t in a_tokens[i1:i2]: add(t, style_normal)
        elif tag == "delete":
            for t in a_tokens[i1:i2]: add(t, style_deleted)
        elif tag == "insert":
            for t in b_tokens[j1:j2]: add(t, style_added)
        elif tag == "replace":
            for t in a_tokens[i1:i2]: add(t, style_deleted)
            for t in b_tokens[j1:j2]: add(t, style_added)

def write_sentence_aware_diff_with_ids(doc: Document, a_idx, a_text, b_idx, b_text):
    hdr = doc.add_paragraph()
    hdr_run = hdr.add_run(f"[A#{a_idx if a_idx is not None else '-'} | B#{b_idx if b_idx is not None else '-'}]")
    hdr_run.italic = True

    # insert/delete
    if a_text is None and b_text is not None:
        par = doc.add_paragraph()
        for tok in tokenize_words(b_text):
            r = par.add_run(tok + " "); style_added(r)
        return

    if b_text is None and a_text is not None:
        par = doc.add_paragraph()
        for tok in tokenize_words(a_text):
            r = par.add_run(tok + " "); style_deleted(r)
        return

    # Aware word/sentence diff when both exist
    r = ratio(a_text, b_text)
    if r >= 0.95:
        par = doc.add_paragraph()
        write_word_diff(par, a_text, b_text)
        return

    s1 = split_sentences(a_text)
    s2 = split_sentences(b_text)
    sm = SequenceMatcher(None, s1, s2, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                par = doc.add_paragraph()
                write_word_diff(par, s1[i1 + k], s2[j1 + k])
        elif tag == "delete":
            for k in range(i2 - i1):
                par = doc.add_paragraph()
                for tok in tokenize_words(s1[i1 + k]):
                    r = par.add_run(tok + " "); style_deleted(r)
        elif tag == "insert":
            for k in range(j2 - j1):
                par = doc.add_paragraph()
                for tok in tokenize_words(s2[j1 + k]):
                    r = par.add_run(tok + " "); style_added(r)
        elif tag == "replace":
            par = doc.add_paragraph()
            write_word_diff(par, " ".join(s1[i1:i2]), " ".join(s2[j1:j2]))

# DOCX / Excel report

@api_view(["POST"])
@permission_classes([AllowAny])
def compare(request):

    file1 = request.FILES["first"]
    file2 = request.FILES["second"]
    parameters = json.loads(request.data["json"])

    equal_ratio = parameters["equal_ratio"]
    weak_equal_ratio = parameters["weak_equal_ratio"]
    output_type = parameters["output_type"]
    
    lines1 = read_docx_lines_with_index(file1)
    lines2 = read_docx_lines_with_index(file2)

    # Auto Ratio
    if equal_ratio is None or weak_equal_ratio is None:
        ar, wr = auto_thresholds(lines1, lines2)
        equal_ratio = ar if equal_ratio is None else equal_ratio
        weak_equal_ratio = wr if weak_equal_ratio is None else weak_equal_ratio

    aligned = align_paragraphs_indexed(lines1, lines2, equal_ratio, weak_equal_ratio)

    # DOCX
    if output_type == "word":
        doc = Document()
        doc.add_heading("Karşılaştırma Raporu (Gelişmiş Redline + Otomatik Eşik + ID)", level=1)
        p = doc.add_paragraph()
        p.add_run(f"Kaynak: {file1}  →  Hedef: {file2}").italic = True
        p = doc.add_paragraph()
        p.add_run(f"equal_ratio={equal_ratio:.3f}  weak_equal_ratio={weak_equal_ratio:.3f}").italic = True
        add_legend(doc)
        doc.add_paragraph()

    stats = {"equal": 0, "insert": 0, "delete": 0, "replace": 0}
    excel_rows = []

    for a_idx, a_text, b_idx, b_text, tag in aligned:
        stats[tag] += 1

        if output_type == "word": # DOCX content
            if tag == "equal":
                write_sentence_aware_diff_with_ids(doc, a_idx, a_text, b_idx, b_text) # To ignore equal lines, delete it
            else:
                write_sentence_aware_diff_with_ids(doc, a_idx, a_text, b_idx, b_text)
        elif output_type == "excel": # Excel content
            excel_rows.append({
                "Tag": tag,                    # equal / insert / delete / replace
                "A_Index": a_idx,
                "B_Index": b_idx,
                "A_Text": a_text,
                "B_Text": b_text,
                "A_Len": len(a_text or ""),
                "B_Len": len(b_text or ""),
                "Similarity": ratio(a_text or "", b_text or "") if (a_text and b_text) else None
            })

    if output_type == "word":
        # Summary Page
        doc.add_page_break()
        doc.add_heading("Özet / Summary", level=2)
        s = doc.add_paragraph()
        s.add_run(
            f"Eş (equal): {stats['equal']}  |  Eklenen (insert): {stats['insert']}  |  "
            f"Silinen (delete): {stats['delete']}  |  Değiştirilen (replace): {stats['replace']}"
        )

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        res = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        res["Content-Disposition"] = 'attachment; filename="Comparison Result.docx"'
        return res
        

    if output_type == "excel":
        # Excel
        df = pd.DataFrame(excel_rows, columns=[
            "Tag","A_Index","B_Index","A_Text","B_Text","A_Len","B_Len","Similarity"
        ])
        # Secondary summary table
        summary_df = pd.DataFrame([stats]).rename(columns={
            "equal":"Equal","insert":"Insert","delete":"Delete","replace":"Replace"
        })

        buffer = BytesIO()
        write_excel_report_openpyxl(
            out_excel=buffer,
            excel_rows=excel_rows,
            summary_stats=stats,
            table_rows=None
        )
        buffer.seek(0)

        res = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res["Content-Disposition"] = 'attachment; filename="Comparison Result.xlsx"'
        return res

    return Response("Error while comparing files.", status=400)



def write_excel_report_openpyxl(out_excel, excel_rows, summary_stats, table_rows=None):
    # DataFrames
    diff_cols = [
        "Tag","A_Index","B_Index","A_Text","B_Text",
        "A_Len","B_Len","Similarity",
        "ListFlag","ListLevel_A","ListLevel_B","ListTag"
    ]
    
    # Automatically create if no fields exist
    if excel_rows and not any(("ListFlag" in r) for r in excel_rows):
        for r in excel_rows:
            r.setdefault("ListFlag", None)
            r.setdefault("ListLevel_A", None)
            r.setdefault("ListLevel_B", None)
            r.setdefault("ListTag", None)

    diff_df = pd.DataFrame(excel_rows, columns=diff_cols)

    summary_df = pd.DataFrame([{
        "Equal": summary_stats.get("equal", 0),
        "Insert": summary_stats.get("insert", 0),
        "Delete": summary_stats.get("delete", 0),
        "Replace": summary_stats.get("replace", 0),
        "Total": sum(summary_stats.values()) if summary_stats else len(diff_df)
    }])

    # TableDiff Page
    if table_rows:
        table_cols = ["TableIndex","ChangeType","RowKey","ColumnName","OldValue","NewValue"]
        table_df = pd.DataFrame(table_rows, columns=table_cols)
    else:
        table_df = None

    # Writer
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        # Diff
        diff_df.to_excel(writer, index=False, sheet_name="Diff")
        ws = writer.sheets["Diff"]

        # Title freeze and filter
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Auto columns width
        for col_idx, col_name in enumerate(diff_df.columns, start=1):
            max_len = max(
                [len(str(col_name))] +
                [len(str(v)) if v is not None else 0 for v in diff_df[col_name].tolist()]
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(60, max(10, max_len + 2))

        # Title style
        header_fill = PatternFill(start_color="FFDCE6F1", end_color="FFDCE6F1", fill_type="solid")
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")

        # Conditional style for tag column  (color)
        # Assuming A columns is Tag
        last_row = ws.max_row
        tag_range = f"A2:A{last_row}"

        # insert -> green text
        ws.conditional_formatting.add(
            tag_range,
            FormulaRule(formula=[f'ISNUMBER(SEARCH("insert",A2))'], stopIfTrue=False,
                        font=Font(color="FF008000"))
        )
        # delete -> red text
        ws.conditional_formatting.add(
            tag_range,
            FormulaRule(formula=[f'ISNUMBER(SEARCH("delete",A2))'], stopIfTrue=False,
                        font=Font(color="FFFF0000"))
        )
        # replace -> blue text
        ws.conditional_formatting.add(
            tag_range,
            FormulaRule(formula=[f'ISNUMBER(SEARCH("replace",A2))'], stopIfTrue=False,
                        font=Font(color="FF1F4E78"))
        )

        # Data Bar for Similarity
        sim_col_idx = None
        for c_idx, name in enumerate(diff_df.columns, start=1):
            if name == "Similarity":
                sim_col_idx = c_idx
                break
        if sim_col_idx:
            col_letter = get_column_letter(sim_col_idx)
            data_bar_range = f"{col_letter}2:{col_letter}{last_row}"
            ws.conditional_formatting.add(
                data_bar_range,
                DataBarRule(start_type="num", start_value=0,
                            end_type="num", end_value=1, color="FF63BE7B",
                            showValue=True)
            )

        # Summary
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
        ws_sum = writer.sheets["Summary"]
        ws_sum.freeze_panes = "A2"
        ws_sum.auto_filter.ref = ws_sum.dimensions
        for col_idx, col_name in enumerate(summary_df.columns, start=1):
            max_len = max(
                [len(str(col_name))] +
                [len(str(v)) if v is not None else 0 for v in summary_df[col_name].tolist()]
            )
            ws_sum.column_dimensions[get_column_letter(col_idx)].width = min(40, max(10, max_len + 2))
        for cell in ws_sum[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")

        # TableDiff (optional)
        if table_df is not None and len(table_df) > 0:
            table_df.to_excel(writer, index=False, sheet_name="TableDiff")
            ws_tab = writer.sheets["TableDiff"]
            ws_tab.freeze_panes = "A2"
            ws_tab.auto_filter.ref = ws_tab.dimensions
            for col_idx, col_name in enumerate(table_df.columns, start=1):
                max_len = max(
                    [len(str(col_name))] +
                    [len(str(v)) if v is not None else 0 for v in table_df[col_name].tolist()]
                )
                ws_tab.column_dimensions[get_column_letter(col_idx)].width = min(60, max(10, max_len + 2))
            for cell in ws_tab[1]:
                cell.font = Font(bold=True)
                cell.fill = header_fill
                cell.alignment = Alignment(vertical="center")

            # add color to ChangeType column
            last_row_tab = ws_tab.max_row
            chg_col = None
            for i, n in enumerate(table_df.columns, start=1):
                if n == "ChangeType":
                    chg_col = get_column_letter(i)
                    break
            if chg_col:
                rng = f"{chg_col}2:{chg_col}{last_row_tab}"
                ws_tab.conditional_formatting.add(
                    rng,
                    FormulaRule(formula=[f'ISNUMBER(SEARCH("row-inserted",{chg_col}2))'],
                                font=Font(color="FF008000"))
                )
                ws_tab.conditional_formatting.add(
                    rng,
                    FormulaRule(formula=[f'ISNUMBER(SEARCH("row-deleted",{chg_col}2))'],
                                font=Font(color="FFFF0000"))
                )
                ws_tab.conditional_formatting.add(
                    rng,
                    FormulaRule(formula=[f'ISNUMBER(SEARCH("cell-changed",{chg_col}2))'],
                                font=Font(color="FF1F4E78"))
                )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_queue(request):
    file = request.FILES.get("file", None)
    data = {}
    if file:
        data["file"] = {"name": file.name, "content": file.read()}
        data["parameters"] = request.data.get("parameters", None)
    else:
        data = request.data
        
    new_uuid = str(uuid.uuid4())
    cache.set(new_uuid, data)
    return Response(new_uuid)

def translate(request, uuid):
    response = StreamingHttpResponse(translate_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

def translate_action(uuid):
    obj = cache.get(uuid, None)
    if obj:
        try:
            if not obj["file"]:
                yield f'data: {json.dumps({"status": "error", "content": "File not found."})}\n\n'
                return
            
            if obj["parameters"]:
                parameters = json.loads(obj["parameters"])
            else:
                yield f'data: {json.dumps({"status": "error", "content": "Parameters not found."})}\n\n'
                return
            
            translate_type = parameters["translate_type"]
            
            yield f'data: {json.dumps({"status": "progress", "percentage": 0, "content": f"Preparing to translate..."})}\n\n'
            translator = get_text_generator(translate_type)
            translated_docx = translator.translate_docx_req(BytesIO(obj["file"]["content"]))
            
            filename = obj["file"]["name"]
            
            for (status, item) in translated_docx:
                if status == "progress":
                    index, total, ptype = item
                    percentage = int((index / total) * 100)
                    yield f'data: {json.dumps({"status": "progress", "percentage": percentage, "content": f"Translating {ptype}... ({index}/{total})"})}\n\n'
                elif status == "result":
                    encoded = b64encode(item.getvalue()).decode()
                    yield f'data: {json.dumps({"status": "success", "content": encoded, "filename": f"[{translate_type.upper()}] {filename}"})}\n\n'
                    
            return
        except ValueError as e:
            yield f'data: {json.dumps({"status": "error", "content": str(e)})}\n\n'
        except Exception as e:
            print(e)
            yield f'data: {json.dumps({"status": "error", "content": "Something went wrong."})}\n\n'
    else:
        yield f'data: {json.dumps({"status": "error", "content": f"UUID not in the queue: {uuid}"})}\n\n'
        
