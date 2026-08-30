"""Canonical project organization and project-scoped authorization models."""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


ATA_VALIDATOR = RegexValidator(
    r"^[0-9]{2}-[0-9]{2}$",
    message="ATA chapter must consist of four digits (XX-XX).",
)


class Project(models.Model):
    """Business-owned project record keyed to the technical capability catalog."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    enabled = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name", "id"]
        permissions = [
            ("manage_project_roles", "Can manage project role assignments"),
        ]

    def __str__(self):
        return self.name


class ResponsibilityRole(models.TextChoices):
    AS = "AS", "AS"
    CVE = "CVE", "CVE"
    PSK = "PSK", "PSK"
    IPT = "IPT", "IPT"
    SSB = "SSB", "SSB"
    AF = "Air Force", "Air Force"
    PCE = "PCE", "PCE"


class Panel(models.Model):
    """One project-scoped certification panel and ATA chapter."""

    name = models.CharField(max_length=255)
    discipline = models.CharField(max_length=255, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="panels")
    ata = models.CharField(max_length=5, validators=[ATA_VALIDATOR])

    class Meta:
        ordering = ["project__name", "ata", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "ata"],
                name="orgs_unique_project_panel_ata",
            )
        ]

    def __str__(self):
        return f"{self.project.slug}: {self.name}"


class Person(models.Model):
    """Global employee directory entry referenced by project assignments."""

    person_id = models.CharField(unique=True, max_length=32, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    email = models.EmailField(db_index=True)

    class Meta:
        ordering = ["name", "person_id"]
        permissions = [
            ("manage_people_directory", "Can manage the global people directory"),
        ]

    def __str__(self):
        return self.name


class ResponsibleAssignment(models.Model):
    """Assign a directory person to a responsibility within one panel."""

    panel = models.ForeignKey(
        Panel,
        on_delete=models.CASCADE,
        related_name="responsible_assignments",
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="responsible_assignments",
    )
    responsibility_role = models.CharField(
        max_length=32,
        choices=ResponsibilityRole.choices,
    )

    class Meta:
        ordering = ["panel__project__name", "panel__ata", "person__name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["panel", "person", "responsibility_role"],
                name="orgs_unique_panel_person_responsibility",
            )
        ]

    @property
    def project(self):
        return self.panel.project

    def __str__(self):
        return f"{self.person} — {self.get_responsibility_role_display()}"


class ProjectRoleAssignment(models.Model):
    """Grant one domain role to either a user or a group for one project."""

    class Domain(models.TextChoices):
        COMPLIANCE = "compliance", "Compliance documents"
        ORGANIZATION = "organization", "Organization"
        DCC = "dcc", "DCC"

    class Role(models.TextChoices):
        VIEWER = "viewer", "Viewer"
        EDITOR = "editor", "Editor"
        MANAGER = "manager", "Manager"
        OPERATOR = "operator", "Operator"
        PUBLISHER = "publisher", "Publisher"

    VALID_ROLES = {
        Domain.COMPLIANCE: {Role.VIEWER, Role.EDITOR, Role.MANAGER},
        Domain.ORGANIZATION: {Role.VIEWER, Role.MANAGER},
        Domain.DCC: {Role.VIEWER, Role.OPERATOR, Role.PUBLISHER},
    }

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    domain = models.CharField(max_length=16, choices=Domain.choices)
    role = models.CharField(max_length=16, choices=Role.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="project_role_assignments",
    )
    group = models.ForeignKey(
        Group,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="project_role_assignments",
    )

    class Meta:
        ordering = ["project__name", "domain", "role", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False, group__isnull=True) | Q(user__isnull=True, group__isnull=False)),
                name="orgs_project_role_exactly_one_subject",
            ),
            models.UniqueConstraint(
                fields=["project", "domain", "user"],
                condition=Q(user__isnull=False),
                name="orgs_unique_project_domain_user_role",
            ),
            models.UniqueConstraint(
                fields=["project", "domain", "group"],
                condition=Q(group__isnull=False),
                name="orgs_unique_project_domain_group_role",
            ),
        ]

    def clean(self):
        super().clean()
        if (self.user_id is None) == (self.group_id is None):
            raise ValidationError("Exactly one of user or group must be set.")
        if self.role not in self.VALID_ROLES.get(self.domain, set()):
            raise ValidationError({"role": "This role is not valid for the selected domain."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def subject(self):
        return self.user or self.group

    def __str__(self):
        return f"{self.project.slug}:{self.domain}:{self.role}:{self.subject}"
