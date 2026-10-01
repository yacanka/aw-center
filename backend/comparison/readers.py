"""Content-only Word/PDF readers; no macros, OCR, layout or formula execution."""

from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree
import re

from .contracts import CompareError, TextBlock, MAX_BLOCKS, MAX_CHARACTERS, MAX_PAGES, check_limit

WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def read_document(content, family, checkpoint=lambda: None):
    if family == 'word':
        blocks, warnings = read_word(content, checkpoint)
    elif family == 'pdf':
        blocks, warnings = read_pdf(content, checkpoint)
    else:
        raise CompareError('Select a supported document type.')
    check_limit(len(blocks) > MAX_BLOCKS, 'The document exceeds the text block limit.')
    check_limit(sum(len(block.text) for block in blocks) > MAX_CHARACTERS, 'The document exceeds the extracted text limit.')
    if not blocks:
        raise CompareError('No extractable text was found. Scanned documents require OCR, which is not supported.',
                           'COMPARE_TEXT_UNAVAILABLE')
    return blocks, warnings


def paragraph_text(paragraph):
    parts = []
    for node in paragraph.iter():
        if node.tag == WORD_NAMESPACE + 't':
            parts.append(node.text or '')
        elif node.tag == WORD_NAMESPACE + 'tab':
            parts.append('\t')
        elif node.tag in (WORD_NAMESPACE + 'br', WORD_NAMESPACE + 'cr'):
            parts.append('\n')
    return ''.join(parts)


def read_word(content, checkpoint):
    blocks = []
    with ZipFile(BytesIO(content)) as archive:
        parts = ['word/document.xml'] + sorted(name for name in archive.namelist()
                    if re.fullmatch(r'word/(header\d+|footer\d+|footnotes|endnotes)\.xml', name))
        characters = 0
        for name in parts:
            checkpoint()
            root = ElementTree.fromstring(archive.read(name))
            for index, paragraph in enumerate(root.iter(WORD_NAMESPACE + 'p'), 1):
                text = paragraph_text(paragraph)
                characters += len(text)
                check_limit(characters > MAX_CHARACTERS or len(blocks) >= MAX_BLOCKS,
                            'The document exceeds the extracted content limit.')
                if text.strip():
                    blocks.append(TextBlock(text, f'{name.removeprefix("word/")} paragraph {index}'))
    return blocks, []


def page_blocks(text, page):
    # Join wrapped lines within a bounded paragraph; keep the original line
    # breaks in the report, normalize only when calculating similarity.
    blocks = []
    current, start = [], 1
    length = 0
    for index, line in enumerate(text.splitlines(), 1):
        if current and (not line.strip() or length + len(line) > 1500):
            blocks.append(TextBlock('\n'.join(current), f'Page {page}, line {start}'))
            current, length = [], 0
        if line.strip():
            if not current:
                start = index
            current.append(line)
            length += len(line) + 1
    if current:
        blocks.append(TextBlock('\n'.join(current), f'Page {page}, line {start}'))
    return blocks


def read_pdf(content, checkpoint):
    from pypdf import PdfReader

    document = PdfReader(BytesIO(content))
    if document.is_encrypted:
        raise CompareError('Password-protected PDFs are not supported.', 'COMPARE_PDF_ENCRYPTED')
    check_limit(len(document.pages) > MAX_PAGES, 'The PDF exceeds the 1,000-page limit.')
    blocks, warnings = [], []
    characters = 0
    for number, page in enumerate(document.pages, 1):
        checkpoint()
        text = page.extract_text() or ''
        if not text.strip():
            if len(page.images):
                raise CompareError('A PDF page contains images but no extractable text. OCR is required.',
                                   'COMPARE_TEXT_UNAVAILABLE')
            warnings.append(f'Page {number} contains no extractable text; visual content is not compared.')
        characters += len(text)
        blocks.extend(page_blocks(text, number))
        check_limit(characters > MAX_CHARACTERS or len(blocks) > MAX_BLOCKS,
                    'The PDF exceeds the extracted content limit.')
    return blocks, warnings
