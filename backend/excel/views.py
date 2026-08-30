from django.http import HttpResponse

from rest_framework.decorators import api_view
from rest_framework.response import Response

import json
from io import BytesIO
from awcenter.api_errors import error_response
from awcenter.file_security import EXCEL_POLICY, validate_request_upload
from awcenter.spreadsheet_security import spreadsheet_safe_dataframe
from .cover_pages import inspect_workbook_columns


class ExcelCompareInputError(Exception):
    def __init__(self, detail, code="EXCEL_COMPARE_INVALID"):
        super().__init__(detail)
        self.detail = detail
        self.code = code

def read_excel_first_sheet(path):
    import pandas as pd

    df = pd.read_excel(path, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.map(lambda value: value.strip() if isinstance(value, str) else value)
    df = df.fillna("")
    return df

def pick_key_columns(df, key_cols=None):
    if key_cols:
        missing = [c for c in key_cols if c not in df.columns]
        if missing:
            raise ExcelCompareInputError("A selected key column is missing from the workbook.")
        return key_cols
    for k in ["id", "ID", "Id", "iD"]:
        if k in df.columns:
            return [k]
    raise ExcelCompareInputError("Select a key column that exists in both workbooks.")


def parse_compare_parameters(request):
    try:
        parameters = json.loads(request.data["json"])
        key_columns = parameters["keyColumns"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ExcelCompareInputError("Select valid Excel comparison parameters.") from error
    if (
        not isinstance(key_columns, list)
        or not 1 <= len(key_columns) <= 10
        or not all(isinstance(value, str) and 0 < len(value) <= 200 for value in key_columns)
    ):
        raise ExcelCompareInputError("Select between one and ten valid key columns.")
    return key_columns

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

        key_columns = parse_compare_parameters(request)

        old_df = read_excel_first_sheet(first_excel)
        new_df = read_excel_first_sheet(second_excel)
        key_cols = pick_key_columns(old_df, key_columns)

        for k in key_cols:
            if k not in new_df.columns:
                raise ExcelCompareInputError("A selected key column is missing from the workbook.")

        if old_df.duplicated(key_cols).any():
            raise ExcelCompareInputError(
                "The first workbook contains duplicate key values.",
                "EXCEL_COMPARE_DUPLICATE_KEYS",
            )
        if new_df.duplicated(key_cols).any():
            raise ExcelCompareInputError(
                "The second workbook contains duplicate key values.",
                "EXCEL_COMPARE_DUPLICATE_KEYS",
            )

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
            spreadsheet_safe_dataframe(added.reset_index(drop=True)).to_excel(
                xlw, index=False, sheet_name="Added"
            )
            spreadsheet_safe_dataframe(removed.reset_index(drop=True)).to_excel(
                xlw, index=False, sheet_name="Removed"
            )
            spreadsheet_safe_dataframe(unchanged.reset_index(drop=True)).to_excel(
                xlw, index=False, sheet_name="Unchanged"
            )

            spreadsheet_safe_dataframe(updated_rows_old.reset_index(drop=True)).to_excel(
                xlw, index=False, sheet_name="Updated (old value)"
            )
            spreadsheet_safe_dataframe(updated_rows_new.reset_index(drop=True)).to_excel(
                xlw, index=False, sheet_name="Updated (new value)"
            )
            spreadsheet_safe_dataframe(diffs_df).to_excel(
                xlw, index=False, sheet_name="Cell Diffs"
            )

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
    except ExcelCompareInputError as error:
        return error_response(error.detail, error.code, response_status=400)
    except Exception:
        return error_response(
            "The Excel comparison could not be completed with the supplied workbooks.",
            "EXCEL_COMPARE_FAILED",
            response_status=400,
        )
