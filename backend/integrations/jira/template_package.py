"""Validate passive DOCX packages and visit Word stories without extracting files."""

from io import BytesIO
import posixpath
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from zlib import error as ZlibError

from django.core.files.uploadedfile import SimpleUploadedFile
from lxml import etree
from rest_framework.exceptions import ValidationError

from awcenter.file_security import MEBIBYTE, WORD_DOCUMENT_POLICY, UploadSecurityError, validate_uploaded_file

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml."
STORIES = {WORD_TYPE + suffix + "+xml": W + root for suffix, root in (
    ("document.main", "document"), ("header", "hdr"), ("footer", "ftr"),
    ("footnotes", "footnotes"), ("endnotes", "endnotes"),
)}
STORY_ORDER = {kind: index for index, kind in enumerate(STORIES)}
STORY_LABELS = {W + "document": "document body", W + "hdr": "header", W + "ftr": "footer",
                W + "footnotes": "footnotes", W + "endnotes": "endnotes"}
MAX_XML_BYTES = 8 * MEBIBYTE
MAX_TOTAL_XML_BYTES = 48 * MEBIBYTE
MAX_XML_NODES = 200_000
PASSIVE_FIELDS = frozenset(
    "PAGE NUMPAGES SECTION SECTIONPAGES REF PAGEREF TOC SEQ DATE TIME CREATEDATE "
    "SAVEDATE PRINTDATE DOCPROPERTY STYLEREF FILENAME AUTHOR TITLE SUBJECT LASTSAVEDBY "
    "LISTNUM SYMBOL FORMULA IF MERGEFIELD".split()
)
UNSAFE_ELEMENTS = {W + name for name in ("altChunk", "object", "control", "subDoc", "attachedTemplate")}
BLOCKED_TYPES = ("macroenabled", "vbaproject", "vbadata", "activex", "oleobject", "afchunk")
BINARY_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff", "image/x-emf", "image/x-wmf",
    "image/emf", "image/wmf", "application/vnd.openxmlformats-officedocument.wordprocessingml.printersettings",
}


def invalid(message):
    raise ValidationError({"detail": message, "code": "JIRA_TEMPLATE_INVALID"})


def _xml(raw):
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)
    root = etree.fromstring(raw, parser)
    tree = root.getroottree()
    if tree.docinfo.doctype or tree.xpath("boolean(//processing-instruction())"):
        invalid("XML declarations of external content are unsupported.")
    return root


def _parts(archive):
    parts = {}
    seen = set()
    for entry in archive.infolist():
        name = entry.filename
        folded = name.casefold().rstrip("/")
        if (folded in seen or name != entry.orig_filename or "\\" in name or "%" in name or ":" in name
                or posixpath.normpath(name) != name.rstrip("/")
                or entry.flag_bits & (0x20 | 0x40) or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)):
            invalid("The DOCX package contains an ambiguous or unsupported part.")
        seen.add(folded)
        if not entry.is_dir():
            parts[name] = entry
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    if not required <= parts.keys():
        invalid("The DOCX package is missing required parts.")
    return parts


def _manifest(archive, parts):
    part = parts["[Content_Types].xml"]
    if part.file_size > MAX_XML_BYTES:
        invalid("The DOCX manifest exceeds the size limit.")
    root = _xml(archive.read(part))
    if root.tag != CT + "Types":
        invalid("The DOCX content type manifest is invalid.")
    defaults, overrides = {}, {}
    for item in root:
        if not isinstance(item.tag, str):
            continue
        if item.tag == CT + "Default":
            name, mapping = item.get("Extension", "").lower(), defaults
        elif item.tag == CT + "Override":
            name, mapping = item.get("PartName", "").removeprefix("/"), overrides
            if name not in parts:
                invalid("The DOCX manifest refers to a missing part.")
        else:
            invalid("The DOCX content type manifest is invalid.")
        kind = item.get("ContentType", "").lower()
        if not name or not kind or name in mapping or any(marker in kind for marker in BLOCKED_TYPES):
            invalid("The DOCX declares an unsupported content type.")
        mapping[name] = kind
    types = {name: overrides.get(name, defaults.get(name.rsplit(".", 1)[-1].lower(), ""))
             for name in parts if name != part.filename}
    if types["word/document.xml"] != WORD_TYPE + "document.main+xml":
        invalid("An ordinary Word DOCX document is required.")
    return root, types


def _relationships(root, name, parts):
    if root.tag != REL + "Relationships":
        invalid("The DOCX relationship part is invalid.")
    base = posixpath.dirname(posixpath.dirname(name))
    main_document = []
    ids = set()
    for rel in root:
        if not isinstance(rel.tag, str):
            continue
        kind, target, rel_id = rel.get("Type", ""), unquote(rel.get("Target", "")), rel.get("Id")
        if rel.tag != REL + "Relationship" or not rel_id or rel_id in ids or not target:
            invalid("The DOCX relationship part is invalid.")
        ids.add(rel_id)
        uri = urlsplit(target)
        mode = rel.get("TargetMode", "Internal")
        if mode == "External" and kind == OFFICE_REL + "hyperlink" and uri.scheme.lower() in {"http", "https", "mailto"}:
            continue
        if (mode != "Internal" or uri.scheme or uri.netloc or "\\" in target or
                kind.rsplit("/", 1)[-1].lower() in {"attachedtemplate", "oleobject", "package", "afchunk",
                                                      "vbaproject", "control", "subdocument"}):
            invalid("The DOCX contains an active or external resource.")
        resolved = posixpath.normpath(posixpath.join(base, uri.path)).removeprefix("/")
        if resolved not in parts:
            invalid("A DOCX relationship has an invalid target.")
        if kind == OFFICE_REL + "officeDocument":
            main_document.append(resolved)
    if name == "_rels/.rels" and main_document != ["word/document.xml"]:
        invalid("The DOCX package does not identify its main document.")


def _passive_field(instruction, location):
    words = instruction.strip().upper().split(None, 1)
    if not words or words[0] not in PASSIVE_FIELDS:
        invalid(f"The {location} contains an unsupported Word field instruction.")


def _validate_word_content(root, location):
    # Word may split the instruction of a complex field across multiple runs.
    stack = []
    for index, node in enumerate(root.iter(), start=1):
        if index > MAX_XML_NODES:
            invalid("The DOCX XML structure exceeds the size limit.")
        if not isinstance(node.tag, str):
            continue
        if node.tag in UNSAFE_ELEMENTS or node.tag == "{urn:schemas-microsoft-com:office:office}OLEObject":
            invalid("The DOCX contains active content.")
        # Legacy VML images can reference external files without an OPC relationship.
        if node.tag.startswith("{urn:schemas-microsoft-com:") and any(
            etree.QName(key).localname.lower() in {"src", "href"} and not value.startswith("#")
            for key, value in node.attrib.items()
        ):
            invalid("The DOCX contains an external resource.")
        if node.tag == W + "fldSimple":
            _passive_field(node.get(W + "instr", ""), location)
        elif node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                stack.append([])
            elif kind == "end" and stack:
                _passive_field("".join(stack.pop()), location)
            elif kind != "separate" or not stack:
                invalid("The DOCX contains a malformed Word field.")
        elif node.tag in {W + "instrText", W + "delInstrText"}:
            if not stack:
                invalid("The DOCX contains a malformed Word field.")
            stack[-1].append(node.text or "")
    if stack:
        invalid("The DOCX contains an incomplete Word field.")


def _copy_binary(archive, entry, output):
    # Check the CRC even on inspection, but keep large embedded images out of memory.
    with archive.open(entry) as source:
        if output is None:
            while source.read(MEBIBYTE):
                pass
            return
        with output.open(entry.filename, "w") as target:
            while chunk := source.read(MEBIBYTE):
                target.write(chunk)


def _package(archive, output, visitor):
    parts = _parts(archive)
    manifest, types = _manifest(archive, parts)
    visitor(manifest, False, "package manifest")
    total_xml = parts["[Content_Types].xml"].file_size
    if output:
        output.writestr("[Content_Types].xml", archive.read("[Content_Types].xml"))
    # Body, headers, footers, footnotes and endnotes have a stable order even if
    # another editor repacks the ZIP with different member ordering.
    names = sorted(types, key=lambda name: (STORY_ORDER.get(types[name], len(STORIES)), name))
    for name in names:
        kind, entry = types[name], parts[name]
        if any(marker in name.lower() for marker in ("/embeddings/", "/activex/", "vbaproject", "vbadata")):
            invalid("The DOCX contains active content.")
        if kind in BINARY_TYPES and not name.lower().endswith((".xml", ".rels")):
            _copy_binary(archive, entry, output)
            continue
        if not kind.endswith(("+xml", "/xml")) or kind.startswith("image/"):
            invalid("The DOCX contains an unsupported embedded resource.")
        total_xml += entry.file_size
        if entry.file_size > MAX_XML_BYTES or total_xml > MAX_TOTAL_XML_BYTES:
            invalid("The DOCX XML content exceeds the size limit.")
        raw = archive.read(entry)
        root = _xml(raw)
        if name.lower().endswith(".rels"):
            _relationships(root, name, parts)
        story = kind in STORIES
        if story and (root.tag != STORIES[kind] or (root.tag == W + "document" and root.find(W + "body") is None)):
            invalid("The DOCX contains an invalid Word story.")
        label = STORY_LABELS[root.tag] if story else _part_label(name, root)
        _validate_word_content(root, label)
        if visitor(root, story, label):
            raw = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
        if output:
            output.writestr(name, raw)


def _part_label(name, root):
    if name.startswith("docProps/"):
        return "document properties"
    if root.tag == REL + "Relationships":
        return "document relationships"
    return {W + "comments": "comments", W + "settings": "document settings",
            W + "styles": "document styles"}.get(root.tag, "unsupported document part")


def process_package(data, visitor, *, render):
    """Visit each XML part once. Return a fresh package only for generation."""
    if not isinstance(data, bytes):
        invalid("A DOCX document is required.")
    uploaded = SimpleUploadedFile("template.docx", data, content_type="application/octet-stream")
    try:
        validate_uploaded_file(uploaded, WORD_DOCUMENT_POLICY)
        with ZipFile(uploaded) as archive:
            if render:
                result = BytesIO()
                with ZipFile(result, "w", ZIP_DEFLATED) as output:
                    _package(archive, output, visitor)
                if result.tell() > WORD_DOCUMENT_POLICY.maximum_bytes:
                    invalid("The generated DOCX exceeds the document size limit.")
                return result.getvalue()
            _package(archive, None, visitor)
    except UploadSecurityError as exc:
        invalid(str(exc.detail))
    except (BadZipFile, etree.XMLSyntaxError, UnicodeError, EOFError, ZlibError, ValueError):
        invalid("The DOCX package is malformed.")
