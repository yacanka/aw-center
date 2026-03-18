from django.db import models
from common.models import CompDocBase, PanelBase, ResponsibleBase

class CompDoc(CompDocBase):
    tech_doc_no_2 = models.CharField(max_length=64, null=True, blank=True)
    tech_doc_issue_2 = models.CharField(null=True, blank=True)
    delivered_tech_doc_issue_2 = models.CharField(null=True, blank=True)

class Panel(PanelBase):
    pass
    
class Responsible(ResponsibleBase):
    panel = models.ForeignKey(Panel, on_delete=models.CASCADE, related_name="responsibles", null=True, blank=True)
    