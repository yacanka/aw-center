"""Bounded applicable-discipline validation for DOORS objects."""

from .builder_common import attribute_fragments, open_module

CHECK_TEMPLATE = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    {declarations}
    Object object
    int awc_count = 0
    for object in entire(module) do {{
        if (awc_count >= 20) break
        string awc_applicable = object.awc_attribute_0 ""
        string awc_discipline = object.awc_attribute_1 ""
        if (awc_applicable != "Applicable" || !null awc_discipline) continue
        awc_emit("OBJECT\t" (object."Absolute Number" "") "\t" awc_escape(identifier(object)) "\t" (level(object) "") {fields})
        awc_count++
    }}
    if (awc_owns_module) close(module, false)
    awc_ok("DISCIPLINE_CHECK_DONE")
}}
'''.strip()


def check_applicable_disciplines(
    module_path: str,
    applicable_attribute: str = "Applicable or Not Applicable",
    discipline_attribute: str = "Discipline",
) -> str:
    """Return up to 20 applicable objects whose discipline is empty."""
    declarations, fields, _ = attribute_fragments([applicable_attribute, discipline_attribute])
    return CHECK_TEMPLATE.format(
        open_statement=open_module(module_path, "read"),
        declarations=declarations,
        fields="".join(f' "\\t" ({field})' for field in fields),
    )
