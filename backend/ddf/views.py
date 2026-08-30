from django import forms
from django.shortcuts import get_object_or_404

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import ErrorCodes, error_response
from awcenter.pagination import paginated_response
from ddf.models import DDF
from ddf.permissions import DDFPermission, IsDDFOwner
from ddf.serializers import DDFSerializer
from integrations.assessment import AssessmentServiceError, request_assessment

from docx import Document
from collections import OrderedDict
from awcenter.file_security import WORD_POLICY, validate_request_upload


PUBLIC_ENDPOINTS = {}
LOGGER = logging.getLogger(__name__)


class DDFView(APIView):
    permission_classes = [IsAuthenticated, DDFPermission, IsDDFOwner]

    def get(self, request):
        ddfs = DDF.objects.filter(created_by=request.user).order_by("-id")
        return paginated_response(request, ddfs, DDFSerializer)

    def post(self, request):
        serializer = DDFSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        count, _ = DDF.objects.filter(created_by=request.user).delete()
        return Response({"message": f"{count} records deleted successfully."})


class DDFObjView(APIView):
    permission_classes = [IsAuthenticated, DDFPermission, IsDDFOwner]

    def get_ddf(self, request, pk):
        """Return a DDF record after object-level ownership checks."""
        ddf = get_object_or_404(DDF, pk=pk)
        self.check_object_permissions(request, ddf)
        return ddf

    def get(self, request, pk):
        serializer = DDFSerializer(self.get_ddf(request, pk))
        return Response(serializer.data)

    def put(self, request, pk):
        ddf = self.get_ddf(request, pk)
        serializer = DDFSerializer(ddf, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        ddf = self.get_ddf(request, pk)
        serializer = DDFSerializer(ddf, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        ddf = self.get_ddf(request, pk)
        serializer = DDFSerializer(ddf)
        ddf.delete()
        return Response(serializer.data, status=status.HTTP_204_NO_CONTENT)


class UploadForm(forms.Form):
    file = forms.FileField()

@api_view(["POST"])
@permission_classes([IsAuthenticated, DDFPermission])
def upload_ddf(request):
    word_file = validate_request_upload(request, "file", WORD_POLICY)
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        doc = Document(word_file)

        ddf = {}
        content = []

        for i, table in enumerate(doc.tables):
            for row in table.rows:
                row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                row_data = list(OrderedDict.fromkeys(row_data))
                content.append(row_data)

        ddf["project"] = content[0][1]
        ddf["doc_name"] = content[1][1]
        ddf["doc_no"] = content[2][1]
        ddf["doc_issue"] = content[2][3]
        ddf["date"] = content[2][5]
        ddf["commentor"] = content[3][1]
        ddf["comments"] = content[5:]

        serializer = DDFSerializer(data=ddf, context={'request': request})
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DDFPermission])
def ddf_assessment(request):
    ddf_data = request.data
    ddf = get_object_or_404(DDF, id=ddf_data.get("id"))
    if ddf.created_by_id != request.user.id:
        return error_response(
            "You do not have permission to access this DDF.",
            code=ErrorCodes.FORBIDDEN,
            response_status=403,
        )
    comments = ddf_data.get("comments")
    if not isinstance(comments, list) or any(
        not isinstance(comment, (list, tuple)) or len(comment) < 3
        for comment in comments
    ):
        return error_response(
            "Invalid DDF assessment request.",
            code=ErrorCodes.VALIDATION_ERROR,
            response_status=400,
        )

    authority_comments = [
        f"\n{index + 1}) {comment[2]}\n"
        for index, comment in enumerate(comments)
    ]

    try:
        prompt = f"""Doküman Değerlendirme Formu (DDF), Tusaş bağlamında, uçuşa elverişlilik ve sertifikasyon ekipleri tarafından kullanılan, dokümanların içeriğini ve niteliğini objektif bir şekilde değerlendirmek için tasarlanmış bir araçtır.
        Değerlendirmeler, 4 farklı görüş kapsamında verilir:
        1. Teknik Görüş: Format, veri yapılandırması, prosedür ve standartlar, teknik uyumluluk gibi teknik açıdan değerlendirmeyi kapsar.
        2. Bilgi Görüşü: Dokümanın bilgi doğruluğu, kapsamlılığı, konuya uygunluğu ve eksiklik/yanlışlıkları odak noktasıdır. Alan uzmanlığı önemlidir.
        3. Editöryel Görüş: Dil kullanımı, anlaşılırlık, düzen, stil kılavuzlarına uygunluk, genel yazım ve imla gibi editöryel açıdan değerlendirmeyi içerir.
        4. Panel Ekleme/Çıkarma Görüşü: Projenin gereksinim temeline, panelin ekleneceğini ya da çıkarılacağını bildirir.

        Sen DDF görüşlerini sınıflandırma uzmanısın. Sana verilen görüşlerin, 4 görüş tipinden hangisine uygun olduğunu söyleyeceksin. Her görüş için, yalnızca görüş tipini yaz. Her görüş tipini yazarken arasına virgül koy. Açıklama yapma. Yorum yapma. Sadece 4 görüş tipinden birini yaz.
        Görüşler aşağıdaki şekilde numara numara eklenmiştir:
        {authority_comments}"""

        payload = {
            "question": prompt,
            "context_messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "strategy_type": 8,
            "chat_purpose": 1,
            "top_k": 3,
            "num_rerank_candidates": 100,
            "score_threshold": 0.25,
            "max_tokens": 2048,
            "stream": True
        }

        review_types = []
        for text in request_assessment(payload):
            review_types = [review_type.strip() for review_type in text.split(",")]
        if len(review_types) != len(comments):
            raise AssessmentServiceError(
                "The assessment service returned an invalid response.",
                "ASSESSMENT_RESPONSE_INVALID",
                502,
            )

        result = [
            f"[{review}] {comments[index][2]}"
            for index, review in enumerate(review_types)
        ]

        ddf.comment_types = review_types
        ddf.save(update_fields=["comment_types"])

        return Response(result)
    except AssessmentServiceError as error:
        return error_response(
            error.detail,
            code=error.code,
            response_status=error.response_status,
        )
    except Exception as error:
        LOGGER.warning(
            "DDF assessment failed failure_type=%s",
            error.__class__.__name__,
        )
        return error_response(
            "The DDF assessment could not be completed.",
            code="DDF_ASSESSMENT_FAILED",
            response_status=500,
        )
