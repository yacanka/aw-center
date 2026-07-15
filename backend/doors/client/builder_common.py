from pathlib import Path

from .escape import dxl_quote

COMMON_DXL = r'''
pragma runLim, 0

string __aw_escape(string value) {
    if (null value) return "\\N"
    Buffer buffer = create
    int index
    for (index = 0; index < length(value); index++) {
        string character = value[index:index]
        if (character == "\\") buffer += "\\\\"
        else if (character == "\n") buffer += "\\n"
        else if (character == "\r") buffer += "\\r"
        else if (character == "\t") buffer += "\\t"
        else buffer += character
    }
    string result = stringOf(buffer)
    delete buffer
    return result
}

void __aw_error(Stream output, string code, string message) {
    output << "ERR\t" << __aw_escape(code) << "\t" << __aw_escape(message) << "\n"
}

void __aw_ok(Stream output, string message) {
    output << "OK\t" << __aw_escape(message) << "\n"
}
'''.strip()


def wrap_dxl(body: str, result_file: Path) -> str:
    """Wrap an operation body with deterministic result-file handling."""
    return f'''{COMMON_DXL}

string __aw_result_file = {dxl_quote(str(result_file))}
Stream __aw_output = write __aw_result_file

{body}

close __aw_output
oleSetResult("AW_DOORS_OK|" __aw_result_file)
'''.strip()


def open_module(module_path: str, mode: str) -> str:
    """Build an escaped DXL module-open statement."""
    path = dxl_quote(module_path)
    statements = {
        "read": f"Module module = read({path}, false)",
        "edit": f"Module module = edit({path}, false, true)",
        "share": f"Module module = share({path}, false, true)",
    }
    if mode not in statements:
        raise ValueError("Unsupported module mode.")
    return statements[mode]
