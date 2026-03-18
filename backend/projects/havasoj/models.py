from django.db import models
from common.models import CompDocBase, PanelBase, ResponsibleBase

class CompDoc(CompDocBase):
    pass

class Panel(PanelBase):
    pass
    
class Responsible(ResponsibleBase):
    panel = models.ForeignKey(Panel, on_delete=models.CASCADE, related_name="responsibles", null=True, blank=True)
    