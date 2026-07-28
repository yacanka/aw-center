from collections.abc import Iterable

from .builder_common import open_module, attribute_fragments, create_func_declarations
from .escape import dxl_quote

CHECK_APPLICABLE_DISCIPLINES = r'''
{func_declarations}
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    {field_declarations}
    if (null {applicable_var} || null {discipline_var}) {
		awc_error("READ_ATTRIBUTE", "Attribute not found.")
		halt
	}
    Object object
    int awc_count = 0
    bool exists = false
    for object in {iterable} do {{
        if (awc_count >= {limit}) break
		if ({applicable_object} != "Applicable") {
			continue
		}

		if ({discipline_object} != null){
			continue
		}else if(!exists){
			exists = true
		}
	
		print " + " o.("Absolute Number") "\n\n"
        awc_emit("OBJECT\t" (object."Absolute Number" "") "\t" (awc_escape(identifier(object))"") "\t" (level(object) "") {fields})
        awc_count++
    }}
    close(module, false)
    if (exists){
		awc_ok("Some issues were found. Check absolute numbers.")
	}else{
    	awc_ok("No issues found.")
	}
}}
'''.strip()

def check_applicable_disciplines(module_path: str) -> str:
    """Build bounded DXL that lists module objects."""
    attributes = ["Applicable or Not Applicable", "Discipline"]
    declarations, objects, variables = attribute_fragments(attributes)
    return CHECK_APPLICABLE_DISCIPLINES.format(
        func_declarations=create_func_declarations(),
        open_statement=open_module(module_path, "read"),
        declarations=declarations,
        iterable="entire",
        limit=25,
        applicable_var=variables[0],
        discipline_var=variables[1],
        applicable_object=objects[0],
        discipline_object=objects[1],
    )