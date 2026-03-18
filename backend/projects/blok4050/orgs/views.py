from projects.blok4050.models import Panel, Responsible
from projects.blok4050.serializers import PanelSerializer, ResponsibleSerializer

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from common.views import responsible_view_set_factory, panel_view_set_factory

PanelViewSet = panel_view_set_factory(Panel, PanelSerializer, [AllowAny])
ResponsibleViewSet = responsible_view_set_factory(Responsible, ResponsibleSerializer, [AllowAny])