from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.pagination import StandardResultsSetPagination

from .invitation_serializers import (
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationListSerializer,
    InvitationQuerySerializer,
    InvitationTokenSerializer,
)
from .invitation_management import invitation_queryset, revoke_invitation
from .invitation_service import accept_invitation, create_invitation, inspect_invitation
from .permissions import CanInviteUsers
from .throttles import InvitationAcceptanceThrottle, InvitationRateThrottle


class InvitationCollectionView(APIView):
    """List invitation audit records and mint one-time links."""

    permission_classes = [IsAuthenticated, CanInviteUsers]

    def get(self, request):
        """Return a filtered and paginated invitation lifecycle ledger."""

        filters = InvitationQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(
            invitation_queryset(filters.validated_data), request, view=self
        )
        return paginator.get_paginated_response(InvitationListSerializer(page, many=True).data)

    def post(self, request):
        """Create an invitation and reveal its raw link exactly once."""

        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, link = create_invitation(request.user, **serializer.validated_data)
        return Response(
            {
                "invitation_link": link,
                "email": invitation.email,
                "expires_at": invitation.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class InvitationDetailView(APIView):
    """Manage one invitation without ever exposing its token digest."""

    permission_classes = [IsAuthenticated, CanInviteUsers]

    def delete(self, request, invitation_id):
        """Revoke an active invitation idempotently."""

        invitation = revoke_invitation(invitation_id)
        return Response(InvitationListSerializer(invitation).data)


class InvitationInspectView(APIView):
    """Return non-secret registration context for a presented token."""

    permission_classes = [AllowAny]
    throttle_classes = [InvitationRateThrottle]

    def post(self, request):
        """Inspect a token supplied in the body so access logs omit it."""

        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = inspect_invitation(serializer.validated_data["token"])
        return Response({"email": invitation.email, "expires_at": invitation.expires_at})


class InvitationAcceptView(APIView):
    """Create an account by atomically consuming a valid invitation."""

    permission_classes = [AllowAny]
    throttle_classes = [InvitationAcceptanceThrottle]

    def post(self, request):
        """Validate account fields and consume the invitation exactly once."""

        if request.user.is_authenticated:
            raise PermissionDenied(
                "Sign out before accepting an invitation.", code="INVITATION_SESSION_ACTIVE"
            )
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = accept_invitation(serializer.validated_data["token"], serializer.account_data())
        return Response(
            {"detail": "Account created. You can now sign in.", "username": user.username},
            status=status.HTTP_201_CREATED,
        )
