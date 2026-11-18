"""Inspect and fill literal {{field name}} tokens in passive Word DOCX stories."""

from bisect import bisect_right
from collections import Counter, defaultdict
from itertools import accumulate
import re

from lxml import etree

from awcenter.file_security import MEBIBYTE
from integrations.jira.template_package import W, invalid, process_package

MAX_FIELD_NAME_LENGTH = 200
MAX_FIELDS = 256
MAX_VALUE_LENGTH = 32_768
MAX_OCCURRENCES = 4096
MAX_INSERTED_BYTES = 8 * MEBIBYTE
MAX_INSERTED_BREAKS = 32_768
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DELIMITER = re.compile(r"{{|}}")
VISIBLE_BOUNDARIES = {W + tag for tag in ("p", "br", "cr", "tab", "drawing", "pict", "fldChar", "fldSimple")}
UNSUPPORTED_ANCESTORS = {W + tag for tag in ("del", "ins", "moveFrom", "moveTo", "fldSimple")}
STATIC_CONTROL_PROPERTIES = {W + tag for tag in (
    "rPr", "alias", "tag", "id", "lock", "placeholder", "showingPlcHdr", "richText", "text", "temporary",
)}
INVALID_XML_CHAR = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _unsupported(text, location):
    if text and DELIMITER.search(text):
        invalid(f"A placeholder in the {location} appears outside supported Word paragraph text.")


def _tokens(text, location):
    start = None
    for token in DELIMITER.finditer(text):
        if token[0] == "{{" and start is None:
            start = token.start()
            continue
        if token[0] != "}}" or start is None:
            invalid(f"The {location} contains unmatched or nested placeholder delimiters.")
        raw = text[start + 2:token.start()]
        name = raw.strip()
        if (not name or len(name) > MAX_FIELD_NAME_LENGTH or "{" in raw or "}" in raw or
                any(ord(char) < 32 or 127 <= ord(char) <= 159 or char in "\u2028\u2029" for char in raw) or
                (start > 0 and text[start - 1] == "{") or text[token.end():token.end() + 1] == "}"):
            invalid(f"The {location} contains an invalid placeholder name.")
        yield start, token.end(), name
        start = None
    if start is not None:
        invalid(f"A placeholder in the {location} is incomplete or spans unsupported Word content.")


def _text_groups(root, location):
    """Yield adjacent Word text runs sharing a paragraph and inline container."""
    group = []
    owner = None
    field_depth = 0
    unsupported_text = []
    for node in root.iter():
        parent = node.getparent()
        tag = node.tag
        if tag == W + "t" and parent is not None and parent.tag == W + "r":
            container = parent.getparent()
            if not field_depth and container is not None and container.tag in {W + "p", W + "hyperlink", W + "sdtContent"}:
                if unsupported_text:
                    _unsupported("".join(unsupported_text), location)
                    unsupported_text.clear()
                if group and owner is not container:
                    yield group
                    group = []
                owner = container
                group.append(node)
                continue
        if tag in VISIBLE_BOUNDARIES or (parent is not None and parent.tag == W + "r" and tag != W + "rPr"):
            if group:
                yield group
                group = []
        if tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            field_depth += int(kind == "begin") - int(kind == "end")
        if node.text and node.text.strip():
            unsupported_text.append(node.text)
    _unsupported("".join(unsupported_text), location)
    if group:
        yield group


def _write_text(node, text):
    """Use Word line breaks and tabs while inheriting the original run style."""
    parts = re.split(r"(\n|\t)", text)
    node.text = parts[0]
    node.set(XML_SPACE, "preserve")
    previous = node
    for index in range(1, len(parts), 2):
        control = etree.Element(W + ("br" if parts[index] == "\n" else "tab"))
        previous.addnext(control)
        previous = control
        if parts[index + 1]:
            next_text = etree.Element(W + "t", {XML_SPACE: "preserve"})
            next_text.text = parts[index + 1]
            previous.addnext(next_text)
            previous = next_text


def _replace(nodes, edits):
    # Apply edits in original offsets and write each affected node just once.
    # A cross-run substitution inherits the opening run; its suffix keeps its own style.
    for index, spans in edits.items():
        node = nodes[index]
        original, pieces, end = node.text or "", [], 0
        for start, stop, value in spans:
            pieces.extend((original[end:start], value))
            end = stop
        pieces.append(original[end:])
        _write_text(node, "".join(pieces))


def _static_controls(node, location):
    """Find the static rich/plain-text controls enclosing an editable placeholder."""
    controls = []
    for ancestor in node.iterancestors():
        if ancestor.tag in UNSUPPORTED_ANCESTORS:
            invalid(f"A placeholder in the {location} appears in a revision or Word field.")
        if ancestor.tag == W + "sdt":
            props = ancestor.find(W + "sdtPr")
            if props is not None:
                if any(child.tag not in STATIC_CONTROL_PROPERTIES for child in props if isinstance(child.tag, str)):
                    invalid(f"A placeholder in the {location} appears in a bound or unsupported content control.")
                controls.append(props)
    return controls


class _LiteralFields:
    def __init__(self, values=None):
        self.counts = Counter()
        self.occurrences = 0
        self.inserted_bytes = 0
        self.inserted_breaks = 0
        self.values = values

    def _value(self, name):
        if name not in self.values:
            invalid("A value is required for each placeholder.")
        value = self.values[name]
        self.inserted_bytes += len(value.encode("utf-8"))
        self.inserted_breaks += value.count("\n") + value.count("\t")
        if self.inserted_bytes > MAX_INSERTED_BYTES or self.inserted_breaks > MAX_INSERTED_BREAKS:
            invalid("The filled template exceeds the output limit.")
        return value

    def _group(self, nodes, location):
        texts = [node.text or "" for node in nodes]
        text = "".join(texts)
        if not DELIMITER.search(text):
            return False
        controls = _static_controls(nodes[0], location)
        ends = list(accumulate(map(len, texts)))
        edits = defaultdict(list)
        for start, stop, name in _tokens(text, location):
            self.counts[name] += 1
            self.occurrences += 1
            if self.occurrences > MAX_OCCURRENCES or len(self.counts) > MAX_FIELDS:
                invalid("The template contains too many placeholders.")
            if self.values is None:
                continue
            first, last = bisect_right(ends, start), bisect_right(ends, stop - 1)
            value = self._value(name)
            for index in range(first, last + 1):
                base = ends[index - 1] if index else 0
                edits[index].append((max(0, start - base), min(ends[index], stop) - base,
                                     value if index == first else ""))
        _replace(nodes, edits)
        if edits:
            for props in controls:
                hint = props.find(W + "showingPlcHdr")
                if hint is not None:
                    props.remove(hint)
        return bool(edits)

    def visit(self, root, story, location):
        for node in root.iter():
            for value in node.attrib.values():
                _unsupported(value, location)
            _unsupported(node.tail, location)
        if not story:
            _unsupported("".join(root.itertext()), location)
            return False
        # Finish traversing the original story before inserting literal user values.
        groups = list(_text_groups(root, location))
        changed = False
        for group in groups:
            changed = self._group(group, location) or changed
        return changed


def inspect_docx(data: bytes) -> list[dict]:
    """Return distinct placeholder names and counts in first-occurrence order."""
    fields = _LiteralFields()
    process_package(data, fields.visit, render=False)
    return [{"name": name, "count": count} for name, count in fields.counts.items()]


def render_docx(data: bytes, values: dict[str, str]) -> bytes:
    """Fill every placeholder with literal XML-safe text, including blank strings."""
    if not isinstance(values, dict) or len(values) > MAX_FIELDS:
        invalid("Template field values must be an object within the field limit.")
    normalized = {}
    for name, value in values.items():
        if (not isinstance(name, str) or not isinstance(value, str) or len(value) > MAX_VALUE_LENGTH or
                INVALID_XML_CHAR.search(value)):
            invalid("A template field has an invalid text value.")
        normalized[name] = value.replace("\r\n", "\n").replace("\r", "\n")
    fields = _LiteralFields(normalized)
    output = process_package(data, fields.visit, render=True)
    if fields.counts.keys() != normalized.keys():
        invalid("Template field values must match the inspected placeholders.")
    return output
