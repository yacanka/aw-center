from django.shortcuts import render
from django.forms import Form, FileField

from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView 

from .serializers import ProjectSerializer, PanelSerializer, ResponsibleSerializer, PeopleSerializer
from .models import  Project, Panel, Responsible, People

from utils.arrays import find_missing_elements
import pandas as pd

class ProjectViewSet(ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()

class PanelViewSet(ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PanelSerializer
    queryset = Panel.objects.all()

    def get_queryset(self):
        qs = Panel.objects.select_related("project")
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(project__name__iexact=project)
        
        return qs

class ResponsibleViewSet(ModelViewSet):
    permission_classes = [AllowAny]
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
    permission_classes = [AllowAny]
    serializer_class = PeopleSerializer
    queryset = People.objects.all()
    
    def get_queryset(self):
        qs = People.objects.all()
        
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

@api_view(["GET"])
@permission_classes([AllowAny])
def Test(request):
    data = {
        "issue": "Merhaba JSON!",
        "dcc_path": "asdsa/asdh",
        "active": True,
        "url": "http://www.google.com"
    }
    return Response(data)

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
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES["file"]
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