from django.utils import timezone
from django.db import transaction

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReleaseNote, ReleaseNoteSeen
from .serializers import BulkSeenSerializer, ReleaseNoteSerializer


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
        serializer = BulkSeenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        if not ids:
            return Response({"ok": True, "created": 0})

        created_count = 0
        # SQLite uses BEGIN IMMEDIATE: acquire the writer lock before reading
        # existing rows, avoiding a read-to-write lock upgrade under contention.
        with transaction.atomic():
            note_ids = ReleaseNote.objects.filter(
                id__in=ids, is_active=True
            ).order_by("id").values_list("id", flat=True)
            existing = set(
                ReleaseNoteSeen.objects.filter(
                    user=request.user, release_note_id__in=ids
                ).values_list("release_note_id", flat=True)
            )
            for note_id in note_ids:
                if note_id in existing:
                    continue
                # get_or_create resolves unique-key races on PostgreSQL too;
                # its created flag keeps the count exact for this request.
                _, created = ReleaseNoteSeen.objects.get_or_create(
                    user=request.user, release_note_id=note_id
                )
                created_count += int(created)

        return Response({
            "ok": True,
            "created": created_count
        })
