from projects.ozgur.models import CompDoc
from projects.ozgur.serializers import CompDocSerializer, HistorySerializer

from common.compdoc_import_views import upload_compdoc_factory
from common.compdoc_excel_export import excel_creator_factory
from common.views import view_set_factory, view_set_obj_factory, history_view_set_factory, compdoc_fields_view_factory

from rest_framework.permissions import IsAuthenticated

CompDocView = view_set_factory(CompDoc, CompDocSerializer, [IsAuthenticated])
CompDocObjView = view_set_obj_factory(CompDoc, CompDocSerializer, [IsAuthenticated])

CompDocUpload = upload_compdoc_factory(CompDoc, CompDocSerializer, [IsAuthenticated])
ExcelCreator = excel_creator_factory(CompDoc, CompDocSerializer, [IsAuthenticated])

HistoryView = history_view_set_factory(CompDoc, HistorySerializer, [IsAuthenticated])
CompDocFields = compdoc_fields_view_factory(CompDoc, [IsAuthenticated])
