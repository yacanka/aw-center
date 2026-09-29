"""Non-mutating panel resolution and catalog changes for compliance imports."""

from dataclasses import dataclass

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from orgs.ata import normalize_ata_chapter
from orgs.models import Panel
from orgs.serializers import PanelSerializer


@dataclass(frozen=True, slots=True)
class PanelReference:
    panel: Panel | None
    requested_name: str | None = None


class PlannedPanelField(serializers.Field):
    """Accept only internal panel instances during import preview validation.

    The document serializer still applies its project-scoped validate_panel hook.
    HTTP serializers retain their ordinary primary-key field.
    """

    def to_internal_value(self, value):
        if not isinstance(value, Panel):
            raise ValidationError("Invalid planned panel.")
        return value


class ImportPanels:
    def __init__(self, project, *, lock_existing=False):
        self.project = project
        queryset = Panel.objects.filter(project=project).order_by("pk")
        if lock_existing:
            queryset = queryset.select_for_update()
        self.existing = {panel.ata: panel for panel in queryset}
        self.lookup = {}
        for panel in self.existing.values():
            for key in {panel.name.casefold(), panel.ata.casefold()}:
                self.lookup.setdefault(key, []).append(panel)
        self.snapshot = [
            {"id": panel.pk, "ata": panel.ata, "name": panel.name}
            for panel in self.existing.values()
        ]

    def resolve(self, values):
        name = values.get("panel")
        ata_value = values.get("ata")
        if ata_value not in (None, ""):
            return self._resolve_ata(ata_value, name)
        if name in (None, ""):
            return PanelReference(None)
        text = str(name).strip().casefold()
        matches = self.lookup.get(text, [])
        if not matches:
            try:
                panel = self.existing.get(normalize_ata_chapter(name))
            except ValueError:
                panel = None
            matches = [panel] if panel else []
        if len(matches) != 1:
            raise ValidationError({
                "ata": "Provide an ATA chapter and panel name for a new or ambiguous panel."
            })
        return PanelReference(matches[0])

    def _resolve_ata(self, value, name):
        try:
            ata = normalize_ata_chapter(value)
        except ValueError as error:
            raise ValidationError({
                "ata": "Use an ATA chapter such as 27, 2700, 27-00, or 27-10."
            }) from error
        target = self.existing.get(ata)
        if name in (None, ""):
            if target is None:
                raise ValidationError({"panel": "Panel name is required for a new ATA chapter."})
            return PanelReference(target)
        serializer = PanelSerializer(target, data={"name": str(name), "ata": ata})
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        panel = target if target is not None else Panel(project=self.project, name=name, ata=ata)
        return PanelReference(panel, name)

    def changes(self, rows):
        # Only accepted document rows contribute; a rejected row cannot rename a
        # shared panel. Dict replacement preserves the last explicit source name.
        names = {}
        for row in rows:
            reference = row.panel_reference
            if reference.requested_name is not None:
                names[reference.panel.ata] = reference.requested_name
        changes = []
        for ata, name in sorted(names.items()):
            target = self.existing.get(ata)
            if target is not None and target.name == name:
                continue
            changes.append({
                "ata": ata,
                "old_name": target.name if target else None,
                "new_name": name,
                "action": "update" if target else "create",
            })
        return tuple(changes)


def apply_panel_changes(changes, project):
    """Apply a reviewed catalog delta inside the caller's import transaction."""
    resolved = {}
    for change in changes:
        target = (
            Panel.objects.get(project=project, ata=change["ata"])
            if change["action"] == "update" else None
        )
        serializer = PanelSerializer(
            target, data={"name": change["new_name"], "ata": change["ata"]},
            partial=target is not None,
        )
        serializer.is_valid(raise_exception=True)
        resolved[change["ata"]] = serializer.save(project=project)
    return resolved
