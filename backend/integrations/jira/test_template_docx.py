from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase, override_settings
from docx import Document
from lxml import etree
from rest_framework.exceptions import ValidationError

from .template_docx import MAX_VALUE_LENGTH, inspect_docx, render_docx
from .template_package import CT, OFFICE_REL, REL, W, WORD_TYPE


def save(document):
    data = BytesIO()
    document.save(data)
    return data.getvalue()


def make_docx(text):
    doc = Document()
    doc.add_paragraph(text)
    return save(doc)


def update_package(data, *, edit_xml=None, extra=None, omit=()):
    updated = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(updated, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name in omit:
                continue
            raw = source.read(name)
            if name in (edit_xml or {}):
                root = etree.fromstring(raw)
                edit_xml[name](root)
                raw = etree.tostring(root)
            target.writestr(name, raw)
        for name, raw in (extra or {}).items():
            target.writestr(name, raw)
    return updated.getvalue()


class TemplateDocxTests(SimpleTestCase):
    def test_literal_values_order_format_and_original_file(self):
        doc = Document()
        p = doc.add_paragraph()
        p.add_run("Left {").bold = True
        p.add_run("{ Başlık / 1 ").italic = True
        p.add_run("}} right {{boş}}{{boş}} end").underline = True
        p.add_run(" {{başlık / 1}}")
        doc.add_table(rows=1, cols=1).cell(0, 0).text = "{{Başlık / 1}}"
        doc.sections[0].header.paragraphs[0].text = "{{Başlık / 1}}"
        doc.sections[0].footer.paragraphs[0].text = "{{boş}}"
        source = save(doc)
        expected = [{"name": "Başlık / 1", "count": 3}, {"name": "boş", "count": 3},
                    {"name": "başlık / 1", "count": 1}]
        self.assertEqual(inspect_docx(source), expected)
        text = ' <& " {{boş}}\r\nsecond\tline '
        output = render_docx(source, {"Başlık / 1": text, "boş": "", "başlık / 1": "ü"})
        filled = Document(BytesIO(output))
        normalized = text.replace("\r\n", "\n")
        runs = filled.paragraphs[0].runs
        self.assertTrue(runs[0].bold)
        self.assertEqual(runs[0].text, "Left " + normalized)
        self.assertTrue(runs[1].italic)
        self.assertEqual(runs[1].text, "")
        self.assertTrue(runs[2].underline)
        self.assertEqual(runs[2].text, " right  end")
        self.assertEqual(runs[3].text, " ü")
        self.assertEqual(filled.tables[0].cell(0, 0).text, normalized)
        self.assertEqual(filled.sections[0].header.paragraphs[0].text, normalized)
        self.assertEqual(filled.sections[0].footer.paragraphs[0].text, "")
        self.assertEqual(inspect_docx(source), expected)
        with ZipFile(BytesIO(source)) as before, ZipFile(BytesIO(output)) as after:
            self.assertEqual(set(before.namelist()), set(after.namelist()))
            for name in ("word/styles.xml", "word/numbering.xml", "docProps/thumbnail.jpeg"):
                self.assertEqual(before.read(name), after.read(name))

    def test_notes_and_textbox_stories_are_processed_once(self):
        source = make_docx("{{body}}")
        extras = {}
        for kind in ("footnotes", "endnotes"):
            root = etree.Element(W + kind)
            note = etree.SubElement(root, W + kind[:-1], {W + "id": "1"})
            run = etree.SubElement(etree.SubElement(note, W + "p"), W + "r")
            etree.SubElement(run, W + "t").text = "{{notes}}"
            extras[f"word/{kind}.xml"] = etree.tostring(root)

        def manifest(root):
            for kind in ("footnotes", "endnotes"):
                etree.SubElement(root, CT + "Override", PartName=f"/word/{kind}.xml",
                                 ContentType=f"{WORD_TYPE}{kind}+xml")

        def relationships(root):
            for kind in ("footnotes", "endnotes"):
                etree.SubElement(root, REL + "Relationship", Id=kind, Type=OFFICE_REL + kind, Target=kind + ".xml")

        def textbox(root):
            run = root.find(f".//{W}r")
            pict = etree.SubElement(run, W + "pict")
            shape = etree.SubElement(pict, "{urn:schemas-microsoft-com:vml}shape")
            box = etree.SubElement(etree.SubElement(shape, "{urn:schemas-microsoft-com:vml}textbox"), W + "txbxContent")
            p = etree.SubElement(box, W + "p")
            for text in ("{{bo", "x}}"):
                etree.SubElement(etree.SubElement(p, W + "r"), W + "t").text = text

        source = update_package(source, extra=extras, edit_xml={
            "[Content_Types].xml": manifest, "word/document.xml": textbox, "word/_rels/document.xml.rels": relationships,
        })
        self.assertEqual(inspect_docx(source), [{"name": "body", "count": 1}, {"name": "box", "count": 1},
                                                {"name": "notes", "count": 2}])
        output = render_docx(source, {"body": "b", "box": "x", "notes": "n"})
        self.assertEqual(inspect_docx(output), [])
        with ZipFile(BytesIO(output)) as package:
            for name in extras:
                self.assertEqual("".join(etree.fromstring(package.read(name)).itertext()), "n")

    def test_multiple_occurrences_and_empty_text_runs(self):
        doc = Document()
        p = doc.add_paragraph()
        for text in ("", "{{a}}{{b", "", "}}{{a}}", ""):
            p.add_run(text)
        source = save(doc)
        self.assertEqual(inspect_docx(source), [{"name": "a", "count": 2}, {"name": "b", "count": 1}])
        self.assertEqual(Document(BytesIO(render_docx(source, {"a": "A", "b": "B"}))).paragraphs[0].text, "ABA")

    def test_malformed_placeholders_and_unsupported_locations(self):
        for token in ("{{}}", "{{   }}", "{{a{{b}}", "a}}", "{{", "{{{bad}}}", "{{a\tb}}", "{{a\nb}}"):
            with self.subTest(token=token), self.assertRaises(ValidationError):
                inspect_docx(make_docx(token))
        doc = Document()
        doc.add_paragraph("{{a")
        doc.add_paragraph("b}}")
        with self.assertRaises(ValidationError):
            inspect_docx(save(doc))
        doc = Document()
        doc.core_properties.title = "{{silent loss}}"
        with self.assertRaisesRegex(ValidationError, "document properties"):
            inspect_docx(save(doc))
        doc = Document()
        doc.sections[0].header.paragraphs[0].text = "{{partial"
        with self.assertRaisesRegex(ValidationError, "header"):
            inspect_docx(save(doc))
        source = update_package(make_docx("ok"), edit_xml={
            "word/document.xml": lambda root: root.set("label", "{{attribute}}"),
        })
        with self.assertRaises(ValidationError):
            inspect_docx(source)

    def test_rejects_invalid_map_types_unicode_missing_and_extra_keys(self):
        source = make_docx("{{x}}")
        for values in ({}, {"x": "", "y": ""}, {"x": None}, {"x": []}, {"x": True}, {"x": "\x00"},
                       {"x": "\ud800"}, {"x": "a" * (MAX_VALUE_LENGTH + 1)}, []):
            with self.subTest(type=type(values)), self.assertRaises(ValidationError):
                render_docx(source, values)
        self.assertEqual(Document(BytesIO(render_docx(source, {"x": "✓😀"}))).paragraphs[0].text, "✓😀")

    def test_rejects_active_package_types_relationships_contents_and_dtd(self):
        source = make_docx("{{x}}")

        def macro(root):
            root.find(f"{CT}Override[@PartName='/word/document.xml']").set(
                "ContentType", "application/vnd.ms-word.document.macroEnabled.main+xml"
            )

        def attached(root):
            etree.SubElement(root, REL + "Relationship", Id="attached", Type=OFFICE_REL + "attachedTemplate",
                             Target="https://example.invalid/template.dotx", TargetMode="External")

        def embedded(root):
            etree.SubElement(root.find(W + "body"), W + "object")

        for edits, extra, omit in (
            ({"[Content_Types].xml": macro}, {}, ()),
            ({"word/_rels/document.xml.rels": attached}, {}, ()),
            ({"word/document.xml": embedded}, {}, ()),
            ({}, {"word/vbaProject.bin": b""}, ()), ({}, {"../invalid": b""}, ()),
            ({}, {"WORD/DOCUMENT.XML": b""}, ()), ({}, {}, ("_rels/.rels",)),
            ({}, {"word/document.xml": b"<not-xml"}, ("word/document.xml",)),
            ({}, {"word/document.xml": b"<!DOCTYPE ordinary><ordinary/>"}, ("word/document.xml",)),
        ):
            with self.subTest(parts=(list(edits), list(extra), omit)), self.assertRaises(ValidationError):
                inspect_docx(update_package(source, edit_xml=edits, extra=extra, omit=omit))
        with self.assertRaises(ValidationError):
            inspect_docx(b"invalid")

    def test_ordinary_page_field_survives_unsupported_fields_rejected(self):
        def with_field(instruction, result):
            def edit(root):
                p = root.find(f".//{W}p")
                for kind, body in (("begin", None), (None, instruction[:2]), (None, instruction[2:]),
                                   ("separate", None), (None, result), ("end", None)):
                    run = etree.SubElement(p, W + "r")
                    if kind:
                        etree.SubElement(run, W + "fldChar", {W + "fldCharType": kind})
                    else:
                        tag = W + ("t" if body == result else "instrText")
                        etree.SubElement(run, tag).text = body
            return update_package(make_docx("{{x}}"), edit_xml={"word/document.xml": edit})

        self.assertEqual(inspect_docx(with_field(" PAGE ", "1")), [{"name": "x", "count": 1}])
        for instruction, result in (("UNSUPPORTED", "1"), ("PAGE", "{{x}}")):
            with self.subTest(instruction=instruction), self.assertRaises(ValidationError):
                inspect_docx(with_field(instruction, result))

    def test_external_link_is_preserved_but_external_image_is_rejected(self):
        source = make_docx("{{x}}")

        def external(kind):
            def add(root):
                etree.SubElement(root, REL + "Relationship", Id="link", Type=OFFICE_REL + kind,
                                 Target="https://example.invalid/example", TargetMode="External")
            return update_package(source, edit_xml={"word/_rels/document.xml.rels": add})

        linked = external("hyperlink")
        with ZipFile(BytesIO(linked)) as before, ZipFile(BytesIO(render_docx(linked, {"x": "hello"}))) as after:
            self.assertEqual(before.read("word/_rels/document.xml.rels"), after.read("word/_rels/document.xml.rels"))
        with self.assertRaises(ValidationError):
            inspect_docx(external("image"))

    def test_rejects_split_placeholders_in_drawing_text_and_tracked_revisions(self):
        def drawing(root):
            draw = etree.SubElement(root.find(f".//{W}r"), W + "drawing")
            for value in ("{", "{field", "}", "}"):
                etree.SubElement(draw, "{http://schemas.openxmlformats.org/drawingml/2006/main}t").text = value

        def revision(root):
            p = root.find(f".//{W}p")
            insertion = etree.SubElement(p, W + "ins")
            etree.SubElement(etree.SubElement(insertion, W + "r"), W + "t").text = "{{field}}"

        for edit in (drawing, revision):
            with self.subTest(location=edit.__name__), self.assertRaises(ValidationError):
                inspect_docx(update_package(make_docx("regular text"), edit_xml={"word/document.xml": edit}))

    def test_unbound_text_control_is_filled_bound_control_identifies_location(self):
        def control(root):
            p = root.find(f".//{W}p")
            sdt = etree.SubElement(p, W + "sdt")
            props = etree.SubElement(sdt, W + "sdtPr")
            etree.SubElement(props, W + "showingPlcHdr")
            etree.SubElement(props, W + "text")
            container = etree.SubElement(sdt, W + "sdtContent")
            for text in ("{{contr", "ol}}"):
                etree.SubElement(etree.SubElement(container, W + "r"), W + "t").text = text

        source = update_package(make_docx("test"), edit_xml={"word/document.xml": control})
        self.assertEqual(inspect_docx(source), [{"name": "control", "count": 1}])
        with ZipFile(BytesIO(render_docx(source, {"control": "value"}))) as result:
            root = etree.fromstring(result.read("word/document.xml"))
            self.assertIsNone(root.find(f".//{W}showingPlcHdr"))
            self.assertIn("value", "".join(root.itertext()))
        bound = update_package(source, edit_xml={
            "word/document.xml": lambda root: etree.SubElement(root.find(f".//{W}sdtPr"), W + "dataBinding")
        })
        with self.assertRaisesRegex(ValidationError, "document body.*content control"):
            inspect_docx(bound)

    def test_upload_and_render_limits(self):
        source = make_docx("{{a}}{{a}}")
        with override_settings(AWCENTER_MAX_DOCUMENT_UPLOAD_BYTES=20), self.assertRaises(ValidationError):
            inspect_docx(source)
        with override_settings(AWCENTER_MAX_ARCHIVE_ENTRIES=1), self.assertRaises(ValidationError):
            inspect_docx(source)
        with patch("integrations.jira.template_docx.MAX_INSERTED_BYTES", 5), self.assertRaises(ValidationError):
            render_docx(source, {"a": "abc"})
        with patch("integrations.jira.template_docx.MAX_OCCURRENCES", 1), self.assertRaises(ValidationError):
            inspect_docx(source)
