from django.utils import timezone
from django.db import transaction

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReleaseNote, ReleaseNoteSeen
from .serializers import ReleaseNoteSerializer


class UnseenReleaseNotesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ReleaseNote.objects.filter(is_active=True).order_by("-published_at")

        seen_ids = set(
            ReleaseNoteSeen.objects.filter(user=request.user)
            .values_list("release_note_id", flat=True)
        )

        unseen = [n for n in qs if n.id not in seen_ids]

        if not unseen:
            return Response(status=204)

        latest = unseen[0]
        mark_seen_ids = [n.id for n in unseen]

        return Response({
            "latest": ReleaseNoteSerializer(latest).data,
            "mark_seen_ids": mark_seen_ids
        })


class MarkSeenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, note_id: int):
        note = ReleaseNote.objects.filter(id=note_id, is_active=True).first()
        if not note:
            return Response({"detail": "Release note not found."}, status=status.HTTP_404_NOT_FOUND)

        obj, created = ReleaseNoteSeen.objects.get_or_create(
            user=request.user,
            release_note=note,
        )

        return Response({"ok": True, "created": created})


class AcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, note_id: int):
        note = ReleaseNote.objects.filter(id=note_id, is_active=True).first()
        if not note:
            return Response({"detail": "Release note not found."}, status=status.HTTP_404_NOT_FOUND)

        obj, _ = ReleaseNoteSeen.objects.get_or_create(
            user=request.user,
            release_note=note,
        )

        obj.acknowledged_at = timezone.now()

        obj.save(update_fields=["acknowledged_at"])
        return Response({"ok": True})


class BulkSeenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"ok": True, "created": 0})

        notes = ReleaseNote.objects.filter(id__in=ids, is_active=True)

        existing = set(
            ReleaseNoteSeen.objects.filter(
                user=request.user,
                release_note_id__in=ids
            ).values_list("release_note_id", flat=True)
        )

        to_create = [
            ReleaseNoteSeen(
                user=request.user,
                release_note=note
            )
            for note in notes
            if note.id not in existing
        ]

        with transaction.atomic():
            ReleaseNoteSeen.objects.bulk_create(to_create)

        return Response({
            "ok": True,
            "created": len(to_create)
        })
