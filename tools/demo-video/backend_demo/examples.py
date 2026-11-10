"""Generate only fictional source material in the recording workspace."""
from datetime import date
from pathlib import Path
import subprocess

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from PIL import Image, ImageDraw, ImageFont

REFERENCE = date(2026, 11, 8)
TEXT = {
    'Atlas belge yönetim planı': 'Atlas document management plan',
    'Amaç ve kapsam': 'Purpose and scope',
    'Bu plan, Atlas Demo Projesi kapsamında belge incelemesini tanımlar.': 'This plan describes document review for the Atlas Demo Project.',
    'Belge listesi': 'Document register',
    'ATL-DOK-001, gözden geçirme ve yayın onayı için izlenir.': 'ATL-DOK-001 is tracked for review and release approval.',
    'Revizyon geçmişi': 'Revision history',
    'A revizyonu 02.11.2026 tarihinde kayıt altına alındı.': 'Revision A was registered on 2 November 2026.',
    'B revizyonu 06.11.2026 tarihinde ikinci incelemeye sunuldu.': 'Revision B was submitted for a second review on 6 November 2026.',
    'Onay': 'Approval',
    'Son sürümü belge sorumlusu ve bağımsız gözden geçiren kişi onaylar.': 'The document owner and the independent reviewer approve the final version.',
    'Ekler': 'Attachments',
    'Ek A, açık maddelerin listesini içerir.': 'Appendix A contains a list of outstanding items.',
}
TITLES = ['Belge yönetim planı', 'Kayıt kabul ölçütleri', 'Gözden geçirme yönergesi', 'Değişiklik bildirim formu', 'Dosya teslim tutanağı', 'Revizyon izleme çizelgesi']
TOPICS = ['Ortak kayıtlar', 'Belge kontrolü', 'Süreç tasarımı', 'Yayın yönetimi', 'Kalite kontrolü', 'Saha geri bildirimi']


def source_title(n):
    return f'{TOPICS[(n-1)//6 % 6]} · {TITLES[(n-1)%6]}'


def workbook(path, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Atlas'
    sheet.append(headers)
    for item in rows:
        sheet.append(item)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='205662')
        sheet.column_dimensions[cell.column_letter].width = max(18, min(44, max(len(str(c.value or '')) for c in sheet[cell.column_letter])+2))
    sheet.freeze_panes = 'B2'
    book.save(path)


def font(size):
    for path in ['/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'DejaVuSans.ttf']:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def slide_image(lines, size=(960,540)):
    image = Image.new('RGB', size, '#f3f6f5')
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, size[0], 20], fill='#27615d')
    draw.text((56, 70), 'ATLAS DEMO PROJESİ', font=font(23), fill='#337169')
    for index, line in enumerate(lines):
        draw.text((56, 142+72*index), line, font=font(36 if index == 0 else 24), fill='#1b373a')
    return image


def write_pdf(path, revision):
    # An ordinary text PDF with selectable, searchable contents on two pages.
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    face = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    fonts = DictionaryObject({NameObject('/F1'): writer._add_object(face)})
    for title, lines in [('Atlas Demo Projesi', ['ATL-DOK-001  |  Belge takip raporu', f'Revizyon {revision}', '1. Belge kontrolu', 'Belge inceleme ve yayin akisinin kaydi.']), ('Acik maddeler', ['2. Gozden gecirme', f'Inceleme donemi: Kasim 2026, surum {revision}', 'Listeye eklenen her belge sorumlusu ile izlenir.'])]:
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): fonts})
        stream = DecodedStreamObject()
        drawing = f'0.08 0.27 0.26 rg 0 805 595 37 re f BT /F1 24 Tf 56 726 Td ({title}) Tj /F1 13 Tf 0 -45 Td '
        drawing += ' 0 -27 Td '.join(f'({line}) Tj' for line in lines) + ' ET'
        stream.set_data(drawing.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)


def make_ddf(path):
    doc = Document()
    table = doc.add_table(rows=7, cols=6)
    for i, label, value in [(0,'Project','Atlas Demo Projesi'), (1,'Document name','Belge yönetim planı'), (3,'Commentor','Deniz Örnek')]:
        table.cell(i,0).text = label
        table.cell(i,1).merge(table.cell(i,5)).text = value
    for i, items in [(2,['Number','ATL-DOK-001','Issue','B','Date','2026-11-02']), (4,['No','Authority','Comment','Response','Status','Reference']), (5,['1','Kalite','Revizyon tarihi eksik.','Tarih eklendi.','Kapalı','Bölüm 2']), (6,['2','Belge kontrol','İmza alanı eklenmeli.','Onay bekleniyor.','Açık','Bölüm 3'])]:
        for cell, value in zip(table.rows[i].cells, items):
            cell.text = value
    table.style = 'Table Grid'
    doc.save(path)


def write_examples(output):
    from excel.cover_pages import REQUIRED_COLUMNS
    output.mkdir(parents=True, exist_ok=True)
    for suffix, rev in [('', 'A'),('-v2','B')]:
        doc = Document()
        for index, line in enumerate(TEXT):
            if (rev == 'A' and line.startswith('B revizyonu')) or (rev == 'B' and line.startswith('A revizyonu')):
                continue
            if index == 0:
                doc.add_heading(line, 0)
            elif len(line) < 20:
                doc.add_heading(line, 1)
            else:
                doc.add_paragraph(line)
        doc.save(output / f'atlas{suffix}.docx')
        write_pdf(output / f'atlas{suffix}.pdf', rev)
        workbook(output/f'atlas{suffix}.xlsx', ['Belge','Başlık','Revizyon'], [[f'ATL-DOK-{n:03}',source_title(n),rev if n in (1,3) else 'A'] for n in range(1,7)])
    workbook(output/'cover.xlsx', REQUIRED_COLUMNS, [[f'ATL-KP-{n:03}', 'B', f'{20+n}', 'Dokümantasyon', source_title(n), '2', f'ATL-GER-{n:03}', '1', f'ATL-DOK-{n:03}', 'B', 'Deniz Örnek', 'Ekin Örnek'] for n in range(1,4)])
    workbook(output/'compliance.xlsx', ['Name','Cover Page Number','Number','Issue','Notes'], [['Yeni revizyon kontrol listesi','ATL-KP-098','ATL-DOK-098','A','Kurgusal içe aktarma örneği.'], ['Kayıt teslim özeti','ATL-KP-099','ATL-DOK-099','A','Kurgusal içe aktarma örneği.']])
    workbook(output/'panels.xlsx', ['Panel','ATA Chapter'], [['Dosya İzleme','98-00']])
    workbook(output/'people.xlsx', ['Person ID','Name','Email'], [['D91001','Ece Örnek','ece.ornek@example.invalid']])
    make_ddf(output / 'ddf.docx')
    slide_image(['Belge yönetim planı', 'ATL-DOK-001 · B revizyonu', 'Denetim ve yayın takibi']).save(output / 'media.png')
    import shutil
    binary = shutil.which('ffmpeg')
    if binary and not (output / 'media.mp4').is_file():
        subprocess.run([binary,'-nostdin','-v','error','-loop','1','-i',str(output/'media.png'),'-t','2','-r','12','-pix_fmt','yuv420p','-c:v','libx264',str(output/'media.mp4')], check=True)
    import importlib.util
    if importlib.util.find_spec('extra_examples'):
        __import__('extra_examples').write(output)
