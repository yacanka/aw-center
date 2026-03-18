from django.db import models

from django.utils import timezone
from django.core.validators import RegexValidator

from simple_history.models import HistoricalRecords

import uuid

STATUS_CHOICES = [
    ('to_be_issued', 'To be Issued'),
    ('airworthiness_review', 'Airworthiness Review'),
    ('to_be_re-submitted', 'To be Re-Submitted'),
    ('to_be_updated', 'To be Updated'),
    ('authority_review', 'Authority Review'),
    ('authority_approved', 'Authority Approved'),
]

LOI_CHOICES = [
    ("1", "1"),
    ("2", "2"),
    ("3", "3"),
    ("not_retained", "Not Retained"),
    ("retained", "Retained"),
]

class CompDocBase(models.Model):
    class Meta:
        abstract = True

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    panel = models.CharField(max_length=128, null=True, blank=True)
    signature_panel = models.JSONField(default=list, null=True, blank=True)
    ata = models.CharField(
        max_length=5,
        default="00-00",
        validators=[
            RegexValidator(r'^[0-9]{2}-[0-9]{2}$', message="Ata chapter must consist of four digits (XX-XX)."),
        ]
    )
    name = models.CharField(max_length=256)
    
    cover_page_no = models.CharField(unique=True, default=uuid.uuid4, max_length=32)
    cover_page_issue = models.CharField(null=True, blank=True)
    tech_doc_no = models.CharField(max_length=64, null=True, blank=True)
    tech_doc_issue = models.CharField(null=True, blank=True)
    delivered_tech_doc_issue = models.CharField(null=True, blank=True)

    responsible = models.CharField(max_length=64, null=True, blank=True)
    cat = models.CharField(max_length=12, null=True, blank=True, choices=LOI_CHOICES)
    moc = models.CharField(max_length=1, null=True, blank=True)
    mom_no = models.CharField(max_length=128, null=True, blank=True)

    requirements = models.JSONField(default=list, null=True, blank=True)
    status_flow = models.JSONField(default=list, null=True, blank=True)

    path = models.CharField(max_length=512, null=True, blank=True)

    notes = models.TextField(null=True, blank=True)

    history = HistoricalRecords(inherit=True)

    created_time = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return self.name

class PanelBase(models.Model):
    class Meta:
        abstract = True

    name = models.CharField()
    discipline = models.CharField()
    ata = models.CharField(
        max_length=5,
        unique=True,
        validators=[
            RegexValidator(r'^[0-9]{2}-[0-9]{2}$', message="Ata chapter must consist of four digits (XX-XX)."),
        ],
    )

    def __str__(self):
        return self.name

class Titles(models.TextChoices):
    AS = "AS", "AS"
    CVE = "CVE", "CVE"
    IPT = "IPT", "IPT"
    SSB = "SSB", "SSB"
    AF = "Air Force", "Air Force"
    PSK = "PSK", "PSK"
    PCE = "PCE", "PCE"

class ResponsibleBase(models.Model):
    class Meta:
        abstract = True
    
    person_id = models.CharField(max_length=6)
    name = models.CharField()
    email = models.EmailField()
    title = models.CharField(choices=Titles.choices)

    def __str__(self):
        return self.name