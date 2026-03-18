# views.py
from io import BytesIO
import math
import json
from zipfile import ZipFile, ZIP_DEFLATED

from django.http import HttpResponse, HttpResponseBadRequest

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView 
from rest_framework import status

from pypdf import PdfReader, PdfWriter
from .comparer.text_comparator import PDFComparator, ComparisonOptions
from .comparer.report_generator import HTMLReportGenerator

def _split_plan(num_pages: int, parts: int | None, pages_per_part: int | None):
    if parts is None and pages_per_part is None:
        raise ValueError("Either 'parts' or 'pages_per_part' must be provided.")

    if parts is None:
        parts = math.ceil(num_pages / max(1, pages_per_part))

    if parts < 1:
        raise ValueError("'parts' must be >= 1.")

    base = num_pages // parts
    rem = num_pages % parts

    counts = [(base + 1 if i < rem else base) for i in range(parts)]
    counts = [c for c in counts if c > 0]
    return counts


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def split_pdf_zip(request):
    f = request.FILES.get("file", None)
    if not f:
        return HttpResponseBadRequest("PDF file is needed.")

    def _to_int(val):
        try:
            return int(val) if val is not None else None
        except ValueError:
            return None

    parameters = request.POST.get("parameters")
    parameters = json.loads(parameters)
    print(parameters)

    parts = _to_int(parameters["parts"])
    pages_per_part = _to_int(parameters["pages_per_parts"])

    try:
        reader = PdfReader(f)
    except Exception as e:
        return HttpResponseBadRequest(f"PDF file can not read: {e}")

    num_pages = len(reader.pages)
    if num_pages == 0:
        return HttpResponseBadRequest("PDF does not contain any page.")

    try:
        plan = _split_plan(num_pages, parts, pages_per_part)
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        start = 0
        for idx, count in enumerate(plan, start=1):
            end = start + count
            writer = PdfWriter()
            for p in range(start, end):
                writer.add_page(reader.pages[p])

            part_buf = BytesIO()
            writer.write(part_buf)
            writer.close()
            part_buf.seek(0)

            zf.writestr(f"part_{idx:02d}_pages_{start+1}-{end}.pdf", part_buf.read())
            start = end

    zip_buffer.seek(0)
    filename = "split_parts.zip"
    resp = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def compare_pdf(request):    
    first_pdf = request.FILES["first"]
    second_pdf = request.FILES["second"]
    
    if not first_pdf or not second_pdf:
        return Response("Pdf not found.", status=400)
    
    try:
        result = comparator.compare(BytesIO(first_pdf.read()), BytesIO(second_pdf.read()))
        summary = result.summary
        
        output = BytesIO()
        if output:
            generator = HTMLReportGenerator()
            generator.save_report(result, output)
        
        resp = HttpResponse(output.getvalue(), content_type="text/html")
        return resp
        
    except Exception as e:
        print(f"Error while comparing pdf: {str(e)}")
        return Response({"message": str(e)}, status=400)

comparator = PDFComparator()