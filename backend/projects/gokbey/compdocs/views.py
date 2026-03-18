from projects.gokbey.models import CompDoc
from projects.gokbey.serializers import CompDocSerializer, HistorySerializer

from common.views import view_set_factory, view_set_obj_factory, upload_compdoc_factory, excel_creator_factory, history_view_set_factory

from rest_framework.permissions import AllowAny, IsAuthenticated

CompDocView = view_set_factory(CompDoc, CompDocSerializer, [AllowAny])
CompDocObjView = view_set_obj_factory(CompDoc, CompDocSerializer, [AllowAny])

CompDocUpload = upload_compdoc_factory(CompDoc, CompDocSerializer, [AllowAny])
ExcelCreator = excel_creator_factory(CompDoc, CompDocSerializer, [AllowAny])

HistoryView = history_view_set_factory(CompDoc, HistorySerializer, [AllowAny])