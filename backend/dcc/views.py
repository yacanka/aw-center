from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404 
from django.core.cache import cache
from django.conf import settings

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from awcenter.api_errors import error_response
from awcenter.file_security import (
    ATTACHMENT_POLICY,
    EXCEL_POLICY,
    PDF_POLICY,
    validate_request_upload,
    validate_uploaded_file,
)
from rest_framework.views import APIView 
from rest_framework import status

from .serializers import JIRA_DCC_Serializer
from .models import JIRA_DCC
from .service.JIRAConnector import JiraConnector, split_text_by_chracter, ISO_time_to_string, parseJiraError
from .service.MailSender import *
from .service.reminder_rate_limit import get_reminder_wait_seconds, reserve_reminder_email_slot
from .permissions import DCCAutomationPermission, DCCPermission, IsDCCOwner
from .services.project_resolver import DccProjectResolutionError, resolve_project_from_jira_components

from .forms import UploadForm
from .parsers import safe_ecd_parse
from .service.text_parsing import (
    check_filename,
    check_panel_text,
    classify_dcc,
    extract_text_from_text,
    find_keyword_list2d,
    make_surname_upper,
    multiselect_to_text,
    parse_labels,
    parse_multiselect,
)
from .service.effectivity import match_effectivity_options, normalize_effectivity_text

from utils.converters import date_parser

from io import BytesIO
import json
import requests
import uuid
from datetime import datetime
import os

from common.views import paginated_response


class ValuesListSerializer:
    """Expose queryset value dictionaries through the serializer data API."""

    def __init__(self, rows, many=True, **kwargs):
        self.data = list(rows)

TEMPLATE_DIR = settings.CUSTOM_TEMPLATE_DIR
JIRA_URL = settings.JIRA_URL
PUBLIC_ENDPOINTS = {}


def _get_project_dcc_parent_path(project_definition):
    """Return configured DCC parent path for a registry project definition."""
    setting_name = project_definition.dcc_parent_path_setting
    if not setting_name:
        return ""
    return str(getattr(settings, setting_name, ""))


class JIRA_DCC_ViewSet(APIView):
    permission_classes = [IsAuthenticated, DCCPermission, IsDCCOwner]

    def get_dcc(self, pk):
        """Return a DCC record after object-level ownership checks."""
        dcc = get_object_or_404(JIRA_DCC, pk=pk)
        self.check_object_permissions(self.request, dcc)
        return dcc

    def get(self, request, pk=None):
        if pk:
            dcc = self.get_dcc(pk)
            serializer = JIRA_DCC_Serializer(dcc)
            return Response(serializer.data)
        dccs = JIRA_DCC.objects.filter(created_by=request.user).order_by("-id")
        issue = request.query_params.get("issue")
        if issue:
            dccs = dccs.filter(issue__icontains=issue)
        return paginated_response(request, dccs, JIRA_DCC_Serializer)

    def post(self, request):
        serializer = JIRA_DCC_Serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        dcc = self.get_dcc(pk)
        serializer = JIRA_DCC_Serializer(dcc, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        dcc = self.get_dcc(pk)
        serializer = JIRA_DCC_Serializer(dcc, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        dcc = self.get_dcc(pk)
        serializer = JIRA_DCC_Serializer(dcc)
        dcc.delete()
        return Response(serializer.data, status=status.HTTP_204_NO_CONTENT)

@api_view(["GET"])
@permission_classes([IsAuthenticated, DCCPermission])
def get_issue_list(request):
    issues = JIRA_DCC.objects.values("issue").order_by("issue")
    return paginated_response(request, issues, ValuesListSerializer)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCPermission])
def get_issue(request):
    try:
        data = request.data
        print(data)
        if "JSESSIONID" in data:
            _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
        else:
            return Response({"message": "JSESSIONID not found in request."}, status=400)
                
        
        _jira.set_issue(data["issue"])
        issue = _jira.get_issue()

        clear_name = issue.fields.customfield_45002.strip().replace("-", "").replace("–", "").replace(" ", "")
        if os.path.exists(data["dcc_path"]):
            issue.raw["dcc_unsigned_path"] = check_filename(data["dcc_path"], f"{clear_name}.docx")
            issue.raw["dcc_signed_path"] =  check_filename(data["dcc_path"], f"{clear_name}.pdf")
            issue.raw["ecd_path"] = check_filename(data["dcc_path"], issue.fields.customfield_45000)
        
        return Response(issue.raw, status=200)
    except json.JSONDecodeError as e:
        return Response(f"Error while loads json: {e}", status=400)
    except Exception as e:
        return Response(f"Something went wrong: {e}", status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCPermission])
def create_issue(request):
    from jira import JIRAError

    try:
        data = request.data
        session_id = data.get("JSESSIONID", None)
        
        if session_id is None:
            return Response({"message": "No session ID found."}, status=400)
        
        _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=session_id)
        
        if _jira is None:
            return Response({"message": "Client error while connecting."}, status=400)
        
        try:
            project_definition = resolve_project_from_jira_components([data.get("project")])
        except DccProjectResolutionError:
            return Response({"message": "Unsupported project."})
        
        issue_fields = {
            "project": "CHN",
            'summary': data["ecd_title"],
            "description": data["ecd_title"],
            'issuetype': {'name': 'Task'},
            "components": [{"name": project_definition.jira_component}],
            "customfield_13054": [{"name": data["requestor"]}], #customfield_10768
            'customfield_45000': data["ecd_no"].split("/")[0].strip(), #customfield_13712
            'customfield_45001': data["ecd_no"].split("/")[1].strip(), #customfield_14297
            'customfield_45002': f"DCC - {project_definition.dcc_label} - {str(datetime.now().year)} - XXX", #customfield_21271
            'customfield_34115': parse_multiselect(resolve_effectivity_value(_jira, data.get("effectivity", ""))),
        }

        issue = _jira.create_issue(issue_fields)

        obj = {
            "issue": issue.key,
            "ecd_name": issue.fields.summary,
            "dcc_path": "//",
            "active": True,
        }

        serializer = JIRA_DCC_Serializer(data=obj)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=201)
        
        return Response(serializer.errors, status=400)
    except json.JSONDecodeError as e:
        return Response({"message": f"Error while loads json: {e}"}, status=400)
    except JIRAError as e:
        return Response({"message": str(e)}, status=400)
    except Exception as e:
        return Response({"message": f"Something went wrong: {e}"}, status=400)

@api_view(["POST"])
def get_folder_status(request):
    try:
        data = json.loads(request.body)
        dcc_file_path = data["dcc_path"] / "asd"
        if os.path.exists():
            pass

        issue = jira.get_issue()
        return Response(issue.raw, status=200)
    except json.JSONDecodeError as e:
        return Response(f"Error while loads json: {e}", status=400)
    except Exception as e:
        return Response(f"Something went wrong: {e}", status=400)

def resolve_effectivity_value(jira_client, raw_effectivity: str) -> str:
    """Normalize effectivity and map it to closest JIRA multiselect options."""
    options = jira_client.get_create_field_allowed_values("CHN", "Task", "customfield_34115")
    return match_effectivity_options(raw_effectivity, options)


def enrich_effectivity(ecd_parsed: dict, session_id: str | None) -> dict:
    """Add normalized and, when possible, JIRA-matched effectivity to parsed ECR data."""
    raw_effectivity = ecd_parsed.get("effectivity", "")
    ecd_parsed["effectivity_original"] = raw_effectivity
    ecd_parsed["effectivity_normalized"] = normalize_effectivity_text(raw_effectivity)
    if session_id:
        jira_client = JiraConnector(server_url=JIRA_URL, jira_session_id=session_id)
        ecd_parsed["effectivity"] = resolve_effectivity_value(jira_client, raw_effectivity)
    else:
        ecd_parsed["effectivity"] = ecd_parsed["effectivity_normalized"]
    return ecd_parsed


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_ecd(request):
    ecd_file = validate_request_upload(request, "file", PDF_POLICY)
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            ecd_parsed = safe_ecd_parse(ecd_file)
            return Response(enrich_effectivity(ecd_parsed, request.POST.get("JSESSIONID")))
        except Exception as e:
            return Response({"message": f"Something went wrong: {e}"}, 400)

    return Response({"message": "Can not parse ECR."}, status=400)
        

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecd_assessment(request):
    try:
        data = request.data

        prompt = f"""Askeride uçuş havacılıkta, ECD (Enginering Change Document) isimle belgeleri değerlendiriyoruz. Sen bir AS (airworthiness specialist) uzmanı olarak aşağıda bilgisi verilen ECD belgesini değerlendireceksin.
        Konuyu 9 farklı panel (disiplin) için ayrı ayrı özel olarak değerlendirmeni istiyorum.
        Paneller isimleri: Structural Panel Assessment, Software Panel Assessment, Systems Engineering Assessment, Avionics & Electrical & E3 Panel Assessment, Flight Panel Assessment, Mission Systems Assessment, Safety Panel Assessment, Human Factors Panel Assessment, ICA (Instructions for Continued Airworthiness) Panel Assessment
        Bu paneller kapsamında ayrı ayrı değerlendirme yaparak part21 standartına göre sınıflandırma yapacaksın. Sınıflandırma türleri: "Major", "Minor additional work", "Minor no effect" olabilir.
        Yanıt formatın her zaman şu şekilde olacak: <Sıra nuamarası>: <Panel Adı>: <Panel Sınıflandırması> - <Açıklama> 
        Değerlendireceğin ECD bilgileri aşağıdadır. Türkçe dilinde yanıt ver. Sadece değerlendirmeni yaz, yalın ve sade ol. Ekstra cümle yazma ve emoji kullanma. 
        ECD adi: {data.get('ecd_title', 'Unknown')}
        ECD Initiator: {data.get('ecd_initiator', 'Unknown')}
        ATA / IDA: {data.get('ata', 'Unknown')}
        sub-ATA: {data.get('subata', 'Unknown')}
        Change Type: {data.get('change_type', 'Unknown')}
        Change Justification: {data.get('change_justification', 'Unknown')}
        Proposed solution / work to be done: {data.get('proposed_solution', 'Unknown')}
        Consequence of nonimplementation: {data.get('consequence', 'Unknown')}
        Impacted groups or parties: {data.get('impacted_groups', 'Unknown')}"""

        url = "http://172.27.160.138:5100/ask"
        data = {
            "question": prompt,
            "context_messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "strategy_type": 8,
            "chat_purpose": 2,
            "top_k": 3,
            "num_rerank_candidates": 100,
            "score_threshold": 0.25,
            "max_tokens": 2048,
            "stream": True
        }

        headers = {'Content-Type': 'application/json; charset=utf-8', 'Accept': '*/*'}
        panel_assessments = []
        with requests.post(url, json=data, headers=headers) as response:
            if response.status_code != 200:
                print(f"Error: API request failed with status code {response.status_code}")
                return Response(f"Error: API request failed with status code {response.status_code}", 400)

            for line in response.iter_lines(decode_unicode=False):
                if line:
                    text = line.decode("utf-8", errors="replace")
                    if check_panel_text(text):
                        text = text.replace("**", "")[3:]
                        panel_assessments.append(text)

        return Response(panel_assessments)
    except Exception as e:
        return Response(f"Something went wrong: {e}", 400)



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_mail(request):
    try:
        data = request.data
        dcc_record = get_object_or_404(request.user.dcc, issue=data["issue"])
        wait_seconds = get_reminder_wait_seconds(dcc_record)
        if wait_seconds:
            return Response({
                "message": "Reminder email can be sent once per DCC record in one hour.",
                "retry_after_seconds": wait_seconds,
            }, status=429)
        
        if data["JSESSIONID"]:
            _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
        else:
            return Response({"message": "JSESSIONID not found in request."}, status=400)
        
        _jira.set_issue(data["issue"])
        ccb_no = str(data["ccb_no"])
        due_date = data["due_date"]

        issue = _jira.get_issue()
        issue_f = issue.fields

        try:
            project_definition = resolve_project_from_jira_components(issue_f.components)
        except DccProjectResolutionError:
            return Response({"message": "Not supported project. Process stopped."}, status=400)

            
        mail_placeholder = {
            "ECD_NAME": issue_f.summary,
            "ECD_NO": f"{issue_f.customfield_45000} / {issue_f.customfield_45001}",
            "JIRA_LINK_NAME": _jira.get_issue_key(),
            "JIRA_LINK": f"{JIRA_URL}/browse/{_jira.get_issue_key()}",
            "DCC_PATH_NAME": issue_f.customfield_45002,
            "CCB_NO": ccb_no,
            "DUE_DATE": due_date,
        }
        

        dcc_parent_path = _get_project_dcc_parent_path(project_definition) + "\\" + str(datetime.now().year)
        dcc_full_path = f"{dcc_parent_path}\\{issue_f.customfield_45002}"
        mail_title = f"[{project_definition.jira_component}] CCB - {ccb_no} toplantı gündemi"
        mail_placeholder["DCC_PATH"] = dcc_full_path
        cc_list = ""

        open_subtask_list = _jira.get_open_subtask()
        to_list = ';'.join([open_subtask.fields.assignee.emailAddress for open_subtask in open_subtask_list])
        #to_list = "yasarcan.kara@tai.com.tr"
        html_file_path = TEMPLATE_DIR / project_definition.mail_template_name
        mail_body = html_to_text(html_file_path)
        mail_body = replace_all_keys(mail_body, mail_placeholder)

        wait_seconds = reserve_reminder_email_slot(dcc_record)
        if wait_seconds:
            return Response({
                "message": "Reminder email can be sent once per DCC record in one hour.",
                "retry_after_seconds": wait_seconds,
            }, status=429)

        SendMail(mail_title, mail_body, to_list, cc_list)

        return Response({"message": "Email was sent via Outlook!"}, status=200)
    except json.JSONDecodeError as e:
        return Response({"message": f"Error while loads json: {e}"}, status=400)
    except KeyError as e:
        return Response({"message": f"Error while accessing data: {e}"}, status=400)
    except Exception as e:
        return Response({"message": f"Something went wrong: {e}"}, status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCPermission])
def add_new_dcc(request):
    try:
        data = request.data
        
        if not "JSESSIONID" in data:
            return Response({"message": "JSESSIONID not found in request."}, status=400)
        
        _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
        _jira.set_issue(data["url"])
        
        user_dcc_list = request.user.dcc.values_list("issue", flat=True)
        print(user_dcc_list, _jira.get_issue_key())
        if _jira.get_issue_key() in user_dcc_list:
            return Response({"message": f"You can not add this issue since alraady added: {_jira.get_issue_key()}"}, status=400)
        issue = _jira.get_issue()
        if issue.fields.issuetype.subtask:
            return Response("You can not add subtask.", status=400)
        obj = {
            "issue": _jira.get_issue_key(),
            "ecd_name": issue.fields.summary,
            "dcc_path": "//",
            "active": True,
        }

        serializer = JIRA_DCC_Serializer(data=obj)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    except json.JSONDecodeError as e:
        return Response(f"Error while loads json: {e}", status=400)
    except Exception as e:
        return Response(f"Something went wrong: {e}", status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def add_attachment(request):
    from jira import JIRAError

    file = validate_request_upload(request, "file", ATTACHMENT_POLICY)
    try:
        data = request.data
        jira_client = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
        jira_client.set_issue(data["issue_key"])
        jira_client.add_attachment(file, filename=file.name)
        detail = f"Attachment named {file.name} added to {data['issue_key']}"
        return Response({"message": detail}, status=201)
    except JIRAError as error:
        return error_response(error.response.text, code="JIRA_ATTACHMENT_REJECTED")
    except (KeyError, ValueError) as error:
        return error_response(str(error), code="JIRA_ATTACHMENT_INVALID")
    except Exception:
        return error_response("Attachment upload failed.", code="JIRA_ATTACHMENT_ERROR")

def create_subtask_action(uuid):
    from jira import JIRAError

    obj = cache.get(uuid, None)
    if obj:
        try:
            if obj["JSESSIONID"]:
                _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=obj["JSESSIONID"])

                current_user = _jira.myself()
                if current_user:
                    yield f'data: {json.dumps({"status": "info", "content": current_user})}\n\n'
                else:
                    yield f'data: {json.dumps({"status": "error", "content": "Error while connecting account."})}\n\n'
                    return
            else:
                yield f'data: {json.dumps({"status": "error", "content": "JSESSIONID not found in request."})}\n\n'
                return

            _jira.set_issue(obj["url"])
            issue = _jira.get_issue()
            if issue.fields.issuetype.subtask:
                yield f'data: {json.dumps({"status": "error", "content": "You can not add subtask to subtask."})}\n\n'
                return
            
            subtasks = obj.get("list", [])
            duedate = obj.get("duedate")
            if subtasks:
                percentage = 0
                step_size = int(100/len(subtasks))
                for subtask in subtasks:
                    yield f'data: {json.dumps({"status": "progress", "percentage": percentage, "content": subtask["summary"]})}\n\n'
                    _jira.create_subtask(
                        summary=subtask.get("summary"),
                        assignee=subtask.get("assignee"),
                        duedate=duedate,
                        extra_fields=subtask.get("fields"),
                    )
                    percentage += step_size
                yield f'data: {json.dumps({"status": "success", "content": "Subtasks created successfully."})}\n\n'
            else:
                yield f'data: {json.dumps({"status": "warning", "content": "No subtask to create."})}\n\n'
        except ValueError as e:
            yield f'data: {json.dumps({"status": "error", "content": str(e)})}\n\n'
        except JIRAError as e:
            yield f'data: {json.dumps({"status": "error", "content": e.text})}\n\n'
        except Exception as e:
            print(e)
            yield f'data: {json.dumps({"status": "error", "content": "Something went wrong."})}\n\n'
    else:
        yield f'data: {json.dumps({"status": "error", "content": f"UUID not in the queue: {uuid}"})}\n\n'
        


@api_view(["GET"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def create_subtask_stream(request, uuid):
    require_queue_owner(str(uuid), request.user.pk)
    response = StreamingHttpResponse(create_subtask_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def create_subtask_excel_action(uuid):
    from jira import JIRAError

    def find_index_by_key(dizi, key, target_value):
        for index, item in enumerate(dizi):
            if key in item and item[key] == target_value:
                return index
        return -1  # Not found

    obj = cache.get(uuid, None)
    if obj:
        try:
            percentage = 0
            yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": percentage, "content": f"Connecting..."})}\n\n'
            parameters = json.loads(obj["parameters"])
            if parameters["JSESSIONID"]:
                _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=parameters["JSESSIONID"])
                
                current_user = _jira.myself()
                if current_user:
                    yield f'data: {json.dumps({"status": "info", "content": current_user})}\n\n'
                else:
                    yield f'data: {json.dumps({"status": "error", "content": "Error while connecting account."})}\n\n'
                    return
            else:
                yield f'data: {json.dumps({"status": "error", "content": "JSESSIONID not found in request."})}\n\n'
                return

            import pandas as pd

            df = pd.read_excel(BytesIO(obj["file"]))
            df = df.where(pd.notnull(df), None)
            
            _jira.set_issue(parameters["url"])
            issue = _jira.get_issue()
            if issue.fields.issuetype.subtask:
                yield f'data: {json.dumps({"status": "error", "content": "You can not add subtask to subtask."})}\n\n'
                
            step_size = int(100/len(df))
            match_list = parameters["list"]

            summary_index = find_index_by_key(match_list, "jira", "summary")
            description_index = find_index_by_key(match_list, "jira", "description")
            
            if summary_index == -1 or description_index == -1:
                yield f'data: {json.dumps({"status": "error", "content": "Summary and description are required."})}\n\n'
                return
            
            summary_col = match_list[summary_index]["excel"]
            description_col = match_list[description_index]["excel"]
            
            assignee_index = find_index_by_key(match_list, "jira", "assignee")
            if assignee_index == -1:
                assignee_col = None
            else:
                assignee_col = match_list[assignee_index]["excel"]
            
            duedate_index = find_index_by_key(match_list, "jira", "duedate")
            if duedate_index == -1:
                duedate_col = None
            else:
                duedate_col = match_list[duedate_index]["excel"]
            
            for index, row in df.iterrows():
                summary = str(row[summary_col])
                description = str(row[description_col])
                
                if assignee_col and row[assignee_col]:
                    assignee = str(row[assignee_col])
                else:
                    assignee = None
                
                if duedate_col and row[duedate_col]:
                    duedate = date_parser(str(row[duedate_col]))
                else:
                    duedate = None

                yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": percentage, "content": f"{summary}"})}\n\n'
                percentage += step_size
                _jira.create_subtask(summary=summary, description=description , assignee=assignee, due_date=duedate)

            yield f'data: {json.dumps({"status": "success", "content": "Subtasks created successfully."})}\n\n'
        except ValueError as e:
            yield f'data: {json.dumps({"status": "error", "content": str(e)})}\n\n'
        except JIRAError as e:
            yield f'data: {json.dumps({"status": "error", "content": e.text})}\n\n'
        except Exception as e:
            print(e)
            yield f'data: {json.dumps({"status": "error", "content": "Something went wrong."})}\n\n'
    else:
        yield f'data: {json.dumps({"status": "error", "content": f"UUID not in the queue: {uuid}"})}\n\n'



@api_view(["GET"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def create_subtask_excel_stream(request, uuid):
    require_queue_owner(str(uuid), request.user.pk)
    response = StreamingHttpResponse(create_subtask_excel_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_session(request):
    from jira import JIRAError

    try:
        session_id = request.GET.get('sessionId', None)
        if session_id:
            client = JiraConnector(server_url=JIRA_URL, jira_session_id=session_id)

            current_user = client.myself()
            if current_user:
                return Response(current_user)
            else:
                return Response({"message": "Session ID is not valid."}, status=400)
        else:
            return Response({"message": "sessionId parameter not found."}, status=400)
    except JIRAError as e:
        return Response({"message": e.text}, status=400)
    except Exception as e:
        print(e)
        return Response({"message": "Something went wrong."}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def get_subtask_fields(request):
    from jira import JIRAError

    session_id = request.data.get("JSESSIONID")
    issue_url = request.data.get("url")
    if not session_id or not issue_url:
        return error_response("JSESSIONID and url are required.", code="SUBTASK_FIELDS_REQUIRED")
    try:
        client = JiraConnector(server_url=JIRA_URL, jira_session_id=session_id)
        client.set_issue(issue_url)
        issue = client.get_issue()
        if issue.fields.issuetype.subtask:
            return error_response("Sub-task links are not supported.", code="SUBTASK_FIELDS_UNSUPPORTED_ISSUE")
        return Response({"issue": client.get_issue_key(), "fields": client.get_subtask_fields()})
    except (ValueError, JIRAError) as error:
        return error_response(str(error), code="SUBTASK_FIELDS_INVALID_REQUEST")
    except Exception as error:
        print(error)
        return error_response("Something went wrong.", code="SUBTASK_FIELDS_ERROR")

@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def create_queue(request):
    file = request.FILES.get("file", None)
    data = {}
    if file:
        validate_uploaded_file(file, EXCEL_POLICY)
        data["file"] = file.read()
        data["parameters"] = request.data.get("parameters", None)
    else:
        data = request.data.copy()
        
    new_uuid = str(uuid.uuid4())
    data["_owner_id"] = request.user.pk
    cache.set(new_uuid, data, timeout=30 * 60)
    return Response(new_uuid)


def require_queue_owner(queue_id, owner_id):
    """Reject missing or cross-user DCC stream queues without revealing existence."""

    payload = cache.get(queue_id)
    if not payload or payload.get("_owner_id") != owner_id:
        raise NotFound("The workflow queue is unavailable.")
    return payload
