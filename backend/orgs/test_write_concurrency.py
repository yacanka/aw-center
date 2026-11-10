"""Preserve disjoint edits made from overlapping database snapshots."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.contrib.auth.models import Group, Permission
from django.db import connections
from django.test import TransactionTestCase

from users.serializers import GroupSerializer
from .models import Panel, Person, Project, ResponsibleAssignment
from .serializers import PanelSerializer, PersonSerializer, ResponsibleAssignmentSerializer


class OrganizationWriteConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.project, _ = Project.objects.get_or_create(
            slug="ozgur", defaults={"name": "Ozgur"},
        )

    def overlapping_patches(self, instance, serializer_class, first_data, second_data):
        """Both connections read old state before the first committed edit."""
        ready = Barrier(2)
        first_saved = Event()

        def update(index, data):
            try:
                stale = type(instance).objects.get(pk=instance.pk)
                serializer = serializer_class(
                    stale, data=data, partial=True, context={"project": self.project},
                )
                serializer.is_valid(raise_exception=True)
                ready.wait(timeout=10)
                if index:
                    self.assertTrue(first_saved.wait(timeout=10))
                serializer.save()
            finally:
                if not index:
                    first_saved.set()
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(update, 0, first_data)
            second = pool.submit(update, 1, second_data)
            first.result(timeout=30)
            second.result(timeout=30)
        instance.refresh_from_db()

    def test_panel_patches_preserve_name_and_discipline(self):
        panel = Panel.objects.create(project=self.project, name="Original", ata="27-00")
        self.overlapping_patches(
            panel, PanelSerializer, {"name": "Updated"}, {"discipline": "Structures"},
        )
        self.assertEqual(panel.name, "Updated")
        self.assertEqual(panel.discipline, "Structures")

    def test_person_patches_preserve_name_and_email(self):
        person = Person.objects.create(person_id="synthetic", name="Original", email="old@example.test")
        self.overlapping_patches(
            person, PersonSerializer, {"name": "Updated"}, {"email": "new@example.test"},
        )
        self.assertEqual(person.name, "Updated")
        self.assertEqual(person.email, "new@example.test")

    def test_assignment_patches_preserve_person_and_role(self):
        panel = Panel.objects.create(project=self.project, name="Panel", ata="27-00")
        original = Person.objects.create(person_id="original", name="Original", email="old@example.test")
        replacement = Person.objects.create(person_id="replacement", name="Replacement", email="new@example.test")
        assignment = ResponsibleAssignment.objects.create(panel=panel, person=original, responsibility_role="AS")
        self.overlapping_patches(
            assignment, ResponsibleAssignmentSerializer,
            {"person_id": replacement.person_id}, {"responsibility_role": "CVE"},
        )
        self.assertEqual(assignment.person_id, replacement.pk)
        self.assertEqual(assignment.responsibility_role, "CVE")

    def test_group_permission_patch_preserves_concurrent_rename(self):
        group = Group.objects.create(name="Original")
        permission = Permission.objects.first()
        self.overlapping_patches(
            group, GroupSerializer, {"name": "Updated"}, {"permission_ids": [permission.pk]},
        )
        self.assertEqual(group.name, "Updated")
        self.assertEqual(list(group.permissions.values_list("pk", flat=True)), [permission.pk])
