from django.db import models

from django.utils import timezone
from django.core.validators import RegexValidator

class Project(models.Model):
    name = models.CharField()
    slug = models.SlugField(unique=True)

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
    name = models.CharField()
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
        constraints = [
            models.UniqueConstraint(fields=["project", "ata"], name="ata_chapter")
        ]

    def __str__(self):
        return self.name

class Responsible(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="people")
    panel = models.ForeignKey(Panel, on_delete=models.CASCADE, related_name="people", null=True, blank=True)

    person_id = models.CharField(max_length=6)
    name = models.CharField()
    email = models.EmailField()
    title = models.CharField(choices=Role.choices)

    def __str__(self):
        return self.name

class People(models.Model):
    person_id = models.CharField(unique=True, max_length=6, db_index=True)
    name = models.CharField(db_index=True)
    email = models.EmailField(db_index=True)

    def __str__(self):
        return self.name