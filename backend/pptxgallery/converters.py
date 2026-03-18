import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
from django.conf import settings
from .models import Presentation, Slide

try:
    import win32com.client  # type: ignore
    import pythoncom  # type: ignore
except ImportError:
    win32com = None
    pythoncom = None

# Gereksinimler:
# - LibreOffice (soffice)
# - poppler-utils (pdftoppm)
# Windows'ta alternatif: yüklü PowerPoint COM ile export (ek fonksiyon altta)

SOFFICE = os.environ.get("SOFFICE_BIN", "soffice")
PDFTOPPM = os.environ.get("PDFTOPPM_BIN", "pdftoppm")


def convert_pptx_to_images(presentation: Presentation, dpi: int = 150):
    try:
        # 1) PPTX -> PDF
        convert_pptx_with_powerpoint(presentation)
        #convert_pptx_with_soffice(presentation)

        presentation.status = "ready"
        presentation.save(update_fields=["status"]) 

    except subprocess.CalledProcessError:
        presentation.status = "failed"
        presentation.save(update_fields=["status"]) 
        raise
    
    


def convert_pptx_with_powerpoint(presentation: Presentation):
    """PowerPoint COM kullanarak PPTX'i slayt görsellerine dönüştürür"""
    if win32com is None or pythoncom is None:
        raise RuntimeError("PowerPoint COM conversion requires a Windows environment.")

    pptx_path = Path(presentation.file.path)
    slides_dir = Path(settings.MEDIA_ROOT) / "slides"
    thumbs_dir = slides_dir / "thumbs"
    slides_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    presentation.status = "converting"
    presentation.save(update_fields=["status"])

    try:
        # PowerPoint uygulamasını başlat (görünmeden)
        pythoncom.CoInitialize()
        app = win32com.client.Dispatch("PowerPoint.Application")
        app.Visible = True

        # PPTX dosyasını aç
        pres = app.Presentations.Open(str(pptx_path), WithWindow=False)

        # Slaytları PNG olarak dışa aktar
        out_dir = slides_dir / f"pres_{presentation.id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        pres.Export(str(out_dir), "PNG")

        pres.Close()
        app.Quit()

        # Oluşan PNG'leri sırala ve veritabanına kaydet
        for idx, img_path in enumerate(sorted(out_dir.glob("*.PNG")), start=1):
            im = Image.open(img_path)
            im_thumb = im.copy()
            im_thumb.thumbnail((512, 512))
            thumb_path = thumbs_dir / f"{presentation.id}_{idx}_thumb.png"
            im_thumb.save(thumb_path)

            Slide.objects.update_or_create(
                presentation=presentation, index=idx,
                defaults={
                    "image": f"slides/pres_{presentation.id}/{img_path.name}",
                    "thumb": f"slides/thumbs/{presentation.id}_{idx}_thumb.png"
                }
            )

        presentation.status = "ready"
        presentation.save(update_fields=["status"])

    except Exception as e:
        presentation.status = "failed"
        presentation.save(update_fields=["status"])
        raise e


def convert_pptx_with_soffice(presentation: Presentation):
    pres_path = presentation.file.path
    workdir = tempfile.mkdtemp(prefix="pptxconv_")
    pdf_path = str(Path(workdir) / "out.pdf")

    presentation.status = "converting"
    presentation.save(update_fields=["status"])
    
    subprocess.check_call([
        SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", workdir, pres_path
    ])
    # LibreOffice bazen çıktı dosya adını korur
    guess_pdf = Path(workdir) / (Path(pres_path).stem + ".pdf")
    if guess_pdf.exists():
        pdf_path = str(guess_pdf)

    # 2) PDF -> PNG'ler
    # out-1.png, out-2.png ...
    out_base = str(Path(workdir) / "out")
    subprocess.check_call([PDFTOPPM, "-png", f"-r", str(dpi), pdf_path, out_base])

    pngs = sorted(Path(workdir).glob("out-*.png"))

    # 3) PNG'leri MEDIA_ROOT'a taşı ve Slide kaydet
    for idx, p in enumerate(pngs, start=1):
        # thumb üret
        im = Image.open(p)
        im_thumb = im.copy()
        im_thumb.thumbnail((512, 512))

        slides_dir = Path(settings.MEDIA_ROOT) / "slides"
        thumbs_dir = slides_dir / "thumbs"
        slides_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        slide_filename = f"{presentation.id}_{idx}.png"
        thumb_filename = f"{presentation.id}_{idx}_thumb.png"

        slide_path = slides_dir / slide_filename
        thumb_path = thumbs_dir / thumb_filename

        im.save(slide_path)
        im_thumb.save(thumb_path)

        Slide.objects.update_or_create(
            presentation=presentation, index=idx,
            defaults={"image": f"slides/{slide_filename}", "thumb": f"slides/thumbs/{thumb_filename}"}
        )
