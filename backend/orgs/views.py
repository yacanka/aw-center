"""Project-scoped organization endpoints."""

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.forms import FileField, Form
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from awcenter.file_security import EXCEL_POLICY, validate_request_upload
from utils.arrays import find_missing_elements

from .access_policy import require_project_role
from .models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment
from .people_search import MAX_QUERY_LENGTH, rank_people
from .serializers import PanelSerializer, PersonSerializer, ResponsibleAssignmentSerializer


SAFE_ACTIONS = {"list", "retrieve"}


class ProjectOrganizationMixin:
    """Resolve one enabled project and apply the canonical organization role."""

    permission_classes = [IsAuthenticated]
    project = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project,
            slug=kwargs["project_slug"],
            enabled=True,
        )
        required_role = (
            ProjectRoleAssignment.Role.VIEWER
            if getattr(self, "action", None) in SAFE_ACTIONS
            else ProjectRoleAssignment.Role.MANAGER
        )
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.ORGANIZATION,
            required_role,
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["project"] = self.project
        return context


class PanelViewSet(ProjectOrganizationMixin, ModelViewSet):
    serializer_class = PanelSerializer

    def get_queryset(self):
        return Panel.objects.filter(project=self.project).select_related("project")

    def perform_create(self, serializer):
        serializer.save(project=self.project)


class ResponsibleAssignmentViewSet(ProjectOrganizationMixin, ModelViewSet):
    serializer_class = ResponsibleAssignmentSerializer

    def get_queryset(self):
        queryset = ResponsibleAssignment.objects.filter(
            panel__project=self.project
        ).select_related("panel", "panel__project", "person")
        panel = self.request.query_params.get("panel")
        if panel:
            queryset = queryset.filter(panel__ata__iexact=panel)
        return queryset


class PersonViewSet(ProjectOrganizationMixin, ModelViewSet):
    serializer_class = PersonSerializer

    def get_queryset(self):
        queryset = Person.objects.order_by("name", "person_id")
        for field in ("person_id", "name", "email"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}__icontains": value})
        return queryset

    def _require_directory_manager(self):
        if not self.request.user.has_perm("orgs.manage_people_directory"):
            raise PermissionDenied(
                detail={
                    "detail": "Global people-directory permission is required.",
                    "code": "PEOPLE_DIRECTORY_PERMISSION_REQUIRED",
                }
            )

    def perform_create(self, serializer):
        self._require_directory_manager()
        serializer.save()

    def perform_update(self, serializer):
        self._require_directory_manager()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_directory_manager()
        try:
            instance.delete()
        except ProtectedError as error:
            raise ValidationError(
                {"person": "Remove this person's assignments before deleting them."}
            ) from error

    def list(self, request, *args, **kwargs):
        search_text = request.query_params.get("search", "").strip()
        if not search_text:
            return super().list(request, *args, **kwargs)
        if len(search_text) > MAX_QUERY_LENGTH:
            raise ValidationError({"search": "Search text must not exceed 100 characters."})
        people = rank_people(self.get_queryset(), search_text)
        page = self.paginate_queryset(people)
        return self.get_paginated_response(
            self.get_serializer(page, many=True).data
        )


class UploadForm(Form):
    file = FileField()


class UploadPeople(APIView):
    permission_classes = [IsAuthenticated]
    reference_columns = ("Person ID", "Name", "Email")

    def post(self, request, project_slug):
        project = get_object_or_404(Project, slug=project_slug, enabled=True)
        require_project_role(
            request.user,
            project,
            ProjectRoleAssignment.Domain.ORGANIZATION,
            ProjectRoleAssignment.Role.MANAGER,
        )
        if not request.user.has_perm("orgs.manage_people_directory"):
            raise PermissionDenied(
                detail={
                    "detail": "Global people-directory permission is required.",
                    "code": "PEOPLE_DIRECTORY_PERMISSION_REQUIRED",
                }
            )

        excel_file = validate_request_upload(request, "file", EXCEL_POLICY)
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            raise ValidationError({"file": "A valid Excel workbook is required."})

        import pandas as pd

        dataframe = pd.read_excel(excel_file).fillna("")
        missing = find_missing_elements(
            dataframe.columns,
            self.reference_columns,
            ignore_case=True,
        )
        if missing:
            raise ValidationError({"columns": f"Missing columns: {missing}"})
        dataframe.columns = [
            str(column).strip().lower().replace(" ", "_")
            for column in dataframe.columns
        ]

        errors = []
        with transaction.atomic():
            for row_number, row in dataframe.iterrows():
                serializer = PersonSerializer(data=row.to_dict())
                if serializer.is_valid():
                    serializer.save()
                else:
                    errors.append(
                        {"row": int(row_number) + 2, "errors": serializer.errors}
                    )
        return Response(
            {
                "detail": "People directory import completed.",
                "code": "PEOPLE_IMPORT_COMPLETED",
                "rejected": errors,
            },
            status=status.HTTP_200_OK,
        )
