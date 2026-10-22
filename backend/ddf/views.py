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
from ddf.assessment_policy import DdfPolicyConfigurationError, assessment_prompt
from ddf.imports import DDFImportError, read_ddf
from ddf.permissions import DDFPermission, IsDDFOwner, DDFAssessmentPermission
from ddf.serializers import DDFSerializer
from integrations.assessment import AssessmentServiceError, request_assessment

from awcenter.file_security import WORD_POLICY, validate_request_upload


PUBLIC_ENDPOINTS = {}
LOGGER = logging.getLogger(__name__)
REVIEW_TYPES = frozenset({
    "Teknik Görüş", "Bilgi Görüşü", "Editöryel Görüş", "Panel Ekleme/Çıkarma Görüşü",
})


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


@api_view(["POST"])
@permission_classes([IsAuthenticated, DDFPermission])
def upload_ddf(request):
    word_file = validate_request_upload(request, "file", WORD_POLICY)
    try:
        ddf = read_ddf(word_file)
    except DDFImportError:
        return error_response(
            "Upload a readable Word document with the supported DDF table layout.",
            code="DDF_IMPORT_INVALID",
            response_status=400,
        )
    serializer = DDFSerializer(data=ddf, context={"request": request})
    if serializer.is_valid():
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DDFAssessmentPermission])
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

    if comments != ddf.comments:
        return assessment_conflict()

    authority_comments = [
        f"\n{index + 1}) {comment[2]}\n"
        for index, comment in enumerate(comments)
    ]

    try:
        prompt = assessment_prompt(authority_comments)

        answer = request_assessment(prompt)
        review_types = [review_type.strip() for review_type in answer.split(",")]
        if len(review_types) != len(comments) or any(
            review not in REVIEW_TYPES for review in review_types
        ):
            raise AssessmentServiceError(
                "The assessment service returned an invalid response.",
                "ASSESSMENT_RESPONSE_INVALID",
                502,
            )

        result = [
            f"[{review}] {comments[index][2]}"
            for index, review in enumerate(review_types)
        ]

        # One conditional SQL write protects SQLite as well as PostgreSQL;
        # never hold a database lock while waiting for an external AI response.
        updated = DDF.objects.filter(
            pk=ddf.pk, created_by=request.user, comments=ddf.comments,
            comment_types=ddf.comment_types,
        ).update(comment_types=review_types)
        if not updated:
            return assessment_conflict()

        return Response(result)
    except DdfPolicyConfigurationError:
        raise
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


def assessment_conflict():
    """Do not disclose stored source text in stale-request errors."""
    return error_response(
        "The DDF changed; reload the record and retry the assessment.",
        code="DDF_ASSESSMENT_CONFLICT", response_status=409,
    )
