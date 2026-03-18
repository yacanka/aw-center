from django.contrib import admin
from .models import ReleaseNote, ReleaseNoteItem, ReleaseNoteSeen


class ReleaseNoteItemInline(admin.TabularInline):
    model = ReleaseNoteItem
    extra = 1
    fields = ("order", "item_type", "heading", "body_md")
    ordering = ("order",)


@admin.register(ReleaseNote)
class ReleaseNoteAdmin(admin.ModelAdmin):
    list_display = ("version", "title", "is_active", "requires_ack", "published_at")
    list_filter = ("is_active", "requires_ack")
    search_fields = ("version", "title")
    inlines = [ReleaseNoteItemInline]


@admin.register(ReleaseNoteSeen)
class ReleaseNoteSeenAdmin(admin.ModelAdmin):
    list_display = ("user", "release_note", "seen_at", "acknowledged_at")
    list_filter = ("release_note",)
    search_fields = ("user__username", "user__email", "release_note__version")

