"""Authenticated API for user-owned document-analysis questions."""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from word.analysis_contracts import AnalysisChecklistError
from word.custom_checks import create_custom_check, delete_custom_check, get_custom_checks


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def custom_check_collection(request):
    """List saved questions or add one to the current user's profile."""

    if request.method == "GET":
        return Response({"results": get_custom_checks(request.user)})
    try:
        check = create_custom_check(request.user, request.data.get("question"))
    except AnalysisChecklistError as error:
        raise ValidationError({"question": str(error)}) from error
    return Response(check, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def custom_check_detail(request, check_id):
    """Delete one question owned by the current authenticated user."""

    if not delete_custom_check(request.user, check_id):
        raise NotFound("The saved analysis question was not found.")
    return Response(status=status.HTTP_204_NO_CONTENT)
