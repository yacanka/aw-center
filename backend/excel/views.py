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
import uuid
import json
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from docxtpl import DocxTemplate
from base64 import b64decode, b64encode
from time import sleep
from utils.arrays import find_missing_elements

class UploadForm(forms.Form):
    file = forms.FileField()

def read_excel_first_sheet(path):
    df = pd.read_excel(path, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    df = df.fillna("")
    return df

def pick_key_columns(df, key_cols=None):
    if key_cols:
        missing = [c for c in key_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Key column is not found: {missing}")
        return key_cols
    for k in ["id", "ID", "Id", "iD"]:
        if k in df.columns:
            return [k]
    raise ValueError("Key column is not set and 'id' not found. Use key_cols=['...'].")

@api_view(["GET"])
@permission_classes([AllowAny])
def test(request):
    return Response("HELP")

@api_view(["POST"])
def get_excel_columns(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES["file"]
        df = pd.read_excel(excel_file)
        return Response(df.columns.tolist())
    
    return Response("Something went wrong.", status=400)

@api_view(["POST"])
def compare(request):
    try:
        first_excel = request.FILES["first"]
        second_excel = request.FILES["second"]
        parameters = json.loads(request.data["json"])
        key_columns = parameters["keyColumns"]

        old_df = read_excel_first_sheet(first_excel)
        new_df = read_excel_first_sheet(second_excel)
        key_cols = pick_key_columns(old_df, key_columns)

        for k in key_cols:
            if k not in new_df.columns:
                raise ValueError(f"Yeni dosyada anahtar sütun eksik: {k}")

        if old_df.duplicated(key_cols).any():
            dups = old_df[old_df.duplicated(key_cols, keep=False)].sort_values(key_cols)
            raise ValueError(f"Eski dosyada anahtar tekrarı var. Düzenleyin.\n{dups}")
        if new_df.duplicated(key_cols).any():
            dups = new_df[new_df.duplicated(key_cols, keep=False)].sort_values(key_cols)
            raise ValueError(f"Yeni dosyada anahtar tekrarı var. Düzenleyin.\n{dups}")

        old_df = old_df.set_index(key_cols, drop=False)
        new_df = new_df.set_index(key_cols, drop=False)

        old_keys = set(old_df.index)
        new_keys = set(new_df.index)

        removed_keys = sorted(old_keys - new_keys)
        added_keys   = sorted(new_keys - old_keys)
        potential_common = sorted(old_keys & new_keys)

        removed = old_df.loc[removed_keys] if removed_keys else old_df.iloc[0:0]
        added   = new_df.loc[added_keys] if added_keys else new_df.iloc[0:0]

        common_cols = [c for c in old_df.columns if c in new_df.columns]

        same_mask = (old_df.loc[potential_common, common_cols]
                     .eq(new_df.loc[potential_common, common_cols])).all(axis=1)
        unchanged = old_df.loc[same_mask.index[same_mask]] if potential_common else old_df.iloc[0:0]
        updated_keys = [idx for idx in potential_common if idx not in unchanged.index]

        updated_rows_old = old_df.loc[updated_keys] if updated_keys else old_df.iloc[0:0]
        updated_rows_new = new_df.loc[updated_keys] if updated_keys else new_df.iloc[0:0]

        diffs_long = []
        if not updated_rows_old.empty:
            for idx in updated_rows_old.index:
                o = updated_rows_old.loc[idx, common_cols]
                n = updated_rows_new.loc[idx, common_cols]
                ne_mask = ~(o == n)
                if ne_mask.any():
                    for col in o.index[ne_mask]:
                        row = {k: idx[i] if isinstance(idx, tuple) else idx for i, k in enumerate(key_cols)}
                        row.update({
                            "column": col,
                            "old": o[col],
                            "new": n[col],
                        })
                        diffs_long.append(row)
        diffs_df = pd.DataFrame(diffs_long, columns=[*key_cols, "column", "old", "new"])

        summary = pd.DataFrame({
            "metric": ["added", "removed", "unchanged", "updated_rows", "updated_cells"],
            "count": [len(added), len(removed), len(unchanged), len(updated_rows_new), len(diffs_df)],
        })

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as xlw:
            summary.to_excel(xlw, index=False, sheet_name="Summary")
            added.reset_index(drop=True).to_excel(xlw, index=False, sheet_name="Added")
            removed.reset_index(drop=True).to_excel(xlw, index=False, sheet_name="Removed")
            unchanged.reset_index(drop=True).to_excel(xlw, index=False, sheet_name="Unchanged")

            updated_rows_old.reset_index(drop=True).to_excel(xlw, index=False, sheet_name="Updated (old value)")
            updated_rows_new.reset_index(drop=True).to_excel(xlw, index=False, sheet_name="Updated (new value)")
            diffs_df.to_excel(xlw, index=False, sheet_name="Cell Diffs")

        buffer.seek(0)

        res = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res["Content-Disposition"] = 'attachment; filename="Compare Result.xlsx"'
        return res

        #return Response({
        #    "summary": summary,
        #    "added": added,
        #    "removed": removed,
        #    "unchanged": unchanged,
        #    "updated_old": updated_rows_old,
        #    "updated_new": updated_rows_new,
        #    "cell_diffs": diffs_df,
        #})
    except Exception as e:
        return Response({"detail": f"Something went wrong: {e}"}, status=400)

reference_list = [
    "Cover Page Number",
    "Cover Page Issue",
    "ATA Chapter",
    "Disciplines",
    "Technical Document Name",
    "CAT",
    "Requirements",
    "MoC",
    "Technical Document Number",
    "Technical Document Issue",
    "AS Name",
    "CVE Name",
]

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_queue(request):
    file = request.FILES.get("file", None)
    data = {}
    if file:
        data["file"] = file.read()
        data["parameters"] = request.data.get("parameters", None)
    else:
        data = request.data
        
    new_uuid = str(uuid.uuid4())
    cache.set(new_uuid, data)
    return Response(new_uuid)

def excel_to_cover_pages_stream(request, uuid):
    response = StreamingHttpResponse(excel_to_cover_pages_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

def excel_to_cover_pages_action(uuid):
    obj = cache.get(uuid, None)
    if obj:
        try:
            parameters = json.loads(obj["parameters"])
            df = pd.read_excel(BytesIO(obj["file"]))
            missing_elements = find_missing_elements(df.columns, reference_list, ignore_case=True)
            if len(missing_elements) > 0:
                print(f"Missing column names exist: {missing_elements}")
                raise ValueError(missing_elements)
            
            yield f'data: {json.dumps({"status": "info", "content": "[]"})}\n\n'
            
            df = df.dropna(subset=["Cover Page Number", "Cover Page Issue"], how="any")
            cover_page_numbers = df["Cover Page Number"]
            
            if not cover_page_numbers.empty:
                cover_page_number = cover_page_numbers.iloc[0]
                print(cover_page_number)
            else:
                yield f'data: {json.dumps({"status": "success", "content": "Cannot detect project type from cover page numbers."})}\n\n'
                return
            
            if "B30" in cover_page_number:
                project_name = "F-16 Block-30 ÖZGÜR-2 Block-30 Özgür-2 Work Package"
            else:
                project_name = "Unkown"
            
            placeholders = [str(column).strip().lower().replace(' ', '_') for column in df.columns]
            
            loader_percentage = 0
            yield f'data: {json.dumps({"status": "progress", "percentage": loader_percentage, "content": "Starting..."})}\n\n'
            cover_page_count = len(df)
            inc_size = int(100 / cover_page_count)
            
            d = DocxTemplate("cover_page_template.docx")
            zip_buffer = BytesIO()
            with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zf:
                for i in range(0, cover_page_count):
                    row = dict(zip(placeholders, df.iloc[i]))
                    row["requirements"] = str(row["requirements"]).strip().replace("\n", ", ").replace(",, ", ", ")
                    row["project_name"] = project_name
                    d.render(row)
                    cover_filename = str(row["cover_page_number"]).split("/")[0] + ".docx"
                    cover_page_buf = BytesIO()
                    d.save(cover_page_buf)
                    cover_page_buf.seek(0)
                    zf.writestr(cover_filename, cover_page_buf.read())
                    
                    loader_percentage += inc_size
                    res_content = f"{row['cover_page_number']} - {row['disciplines']} - {row['technical_document_name']}"
                    yield f'data: {json.dumps({"status": "progress", "percentage": loader_percentage, "content": res_content})}\n\n'
                    sleep(0.1)
                    
            encoded = b64encode(zip_buffer.getvalue()).decode()
            yield f'data: {json.dumps({"status": "success", "content": encoded})}\n\n'
        except ValueError as e:
            print("Unavailable column names. Check the Excel!")
            yield f'data: {json.dumps({"status": "info", "content": str(e)})}\n\n'
            yield f'data: {json.dumps({"status": "error", "content": "Some column names are missing in the Excel file. Please ensure all required columns are present."})}\n\n'
        except Exception as e:
            print(f"Error: {e}")
            yield f'data: {json.dumps({"status": "error", "content": f"Something went wrong: {e}"})}\n\n'
    
    return Response("Something went wrong.", status=400)