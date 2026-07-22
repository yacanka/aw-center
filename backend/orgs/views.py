from django.shortcuts import render
from django.forms import Form, FileField
from awcenter.file_security import EXCEL_POLICY, validate_request_upload

from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from .serializers import PanelSerializer, ResponsibleSerializer, PeopleSerializer
from .models import Panel, Responsible, People
from .people_search import MAX_QUERY_LENGTH, rank_people

from utils.arrays import find_missing_elements

class PanelViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PanelSerializer
    queryset = Panel.objects.all()

    def get_queryset(self):
        qs = Panel.objects.select_related("project")
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(project__name__iexact=project)

        return qs

class ResponsibleViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ResponsibleSerializer
    queryset = Responsible.objects.all()

    def get_queryset(self):
        qs = Responsible.objects.select_related("project", "panel")
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(project__name__iexact=project)

        panel = self.request.query_params.get("panel")
        if panel:
            qs = qs.filter(panel__name__iexact=panel)

        return qs

class PeopleViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PeopleSerializer
    queryset = People.objects.all()

    def list(self, request, *args, **kwargs):
        """Return a normal page or a relevance-ranked search page."""
        search_text = request.query_params.get("search", "").strip()
        if not search_text:
            return super().list(request, *args, **kwargs)
        if len(search_text) > MAX_QUERY_LENGTH:
            raise ValidationError({"search": "Search text must not exceed 100 characters."})

        people = rank_people(self.get_queryset(), search_text)
        page = self.paginate_queryset(people)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def get_queryset(self):
        qs = People.objects.order_by("name", "person_id")

        person_id = self.request.query_params.get("person_id")
        if person_id:
            qs = qs.filter(person_id__icontains=person_id)

        name = self.request.query_params.get("name")
        if name:
            qs = qs.filter(name__icontains=name)

        email = self.request.query_params.get("email")
        if email:
            qs = qs.filter(email__icontains=email)

        return qs

reference_list = [
    "Person ID",
    "Name",
    "Email"
]

class UploadForm(Form):
    file = FileField()

@permission_classes([IsAuthenticated])
class UploadPeople(APIView):
    def post(self, request):
        excel_file = validate_request_upload(request, "file", EXCEL_POLICY)
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            import pandas as pd

            df = pd.read_excel(excel_file)

            missing_elements = find_missing_elements(df.columns, reference_list, ignore_case=True)
            if len(missing_elements) > 0:
                return Response({"message": f"Missing column names exist: {missing_elements}"}, status=400)

            df.columns = [str(column).strip().lower().replace(' ', '_') for column in df.columns]

            df = df.fillna("")

            try:
                error_list = []
                for _, row in df.iterrows():
                    try:
                        serializer = PeopleSerializer(data=row.to_dict())
                        if serializer.is_valid():
                            serializer.save()
                        else:
                            error_list.append({"name": row["name"], "error": serializer.errors})
                    except Exception as e:
                        print(row["name"], e)
                        error_list.append({"name": row["name"], "error": str(e)})
                if error_list:
                    print(error_list)
                    return Response({"message": "Uploaded successfully. But some person can not imported.", "error_list": error_list}, status=201)
                return Response({"message": "Uploaded successfully. Database updated."}, status=201)
            except Exception as e:
                return Response({"message": f"Error while uploading Excel: {e}"}, status=400)
        else:
            return Response({"message": "Not a valid form."}, status=400)
