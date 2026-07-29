from django.db import models

from django.core.validators import RegexValidator

class Project(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

class Role(models.TextChoices):
    AS = "AS", "AS"
    CVE = "CVE", "CVE"
    PSK = "PSK", "PSK"
    IPT = "IPT", "IPT"
    SSB = "SSB", "SSB"
    AF = "Air Force", "Air Force"

class Panel(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="panels")
    ata = models.CharField(
        max_length=5,
        default="00-00",
        validators=[
            RegexValidator(r'^[0-9]{2}-[0-9]{2}$', message="Ata chapter must consist of four digits (XX-XX)."),
        ],
    )

    class Meta:
        ordering = ["project__name", "ata", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "ata"], name="ata_chapter")
        ]

    def __str__(self):
        return self.name

class Responsible(models.Model):
    class Meta:
        ordering = ["project__name", "person__name", "person__person_id", "id"]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="people")
    panel = models.ForeignKey(Panel, on_delete=models.CASCADE, related_name="people", null=True, blank=True)

    person = models.ForeignKey(
        "People",
        on_delete=models.PROTECT,
        related_name="legacy_responsible_assignments",
    )
    title = models.CharField(max_length=32, choices=Role.choices)

    @property
    def name(self):
        """Return the current directory name."""
        return self.person.name

    @property
    def email(self):
        """Return the current directory email."""
        return self.person.email

    def __str__(self):
        return self.name

class People(models.Model):
    class Meta:
        ordering = ["name", "person_id"]

    person_id = models.CharField(unique=True, max_length=6, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    email = models.EmailField(db_index=True)

    def __str__(self):
        return self.name
