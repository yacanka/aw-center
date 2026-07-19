from django.http import HttpResponse

from rest_framework.decorators import api_view
from rest_framework.response import Response

import json
from io import BytesIO
from awcenter.file_security import EXCEL_POLICY, validate_request_upload
from .cover_pages import inspect_workbook_columns

def read_excel_first_sheet(path):
    import pandas as pd

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

@api_view(["POST"])
def get_excel_columns(request):
    excel_file = validate_request_upload(request, "file", EXCEL_POLICY)
    columns, _missing = inspect_workbook_columns(excel_file)
    return Response(columns)

@api_view(["POST"])
def compare(request):
    first_excel = validate_request_upload(request, "first", EXCEL_POLICY)
    second_excel = validate_request_upload(request, "second", EXCEL_POLICY)
    try:
        import pandas as pd

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
