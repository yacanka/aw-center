from projects.aesa.models import Panel, Responsible
from projects.aesa.serializers import PanelSerializer, ResponsibleSerializer

from rest_framework.permissions import IsAuthenticated
from common.views import responsible_view_set_factory, panel_view_set_factory

PanelViewSet = panel_view_set_factory(Panel, PanelSerializer, [IsAuthenticated])
ResponsibleViewSet = responsible_view_set_factory(Responsible, ResponsibleSerializer, [IsAuthenticated])
