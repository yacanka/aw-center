from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404 
from django.core.cache import cache
from django.conf import settings

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView 
from rest_framework import status

from .serializers import JIRA_DCC_Serializer
from .models import JIRA_DCC
from .service.JIRAConnector import JiraConnector, split_text_by_chracter, ISO_time_to_string, parseJiraError
from .service.MailSender import *
from .permissions import DCCPermission, IsOwner

from .forms import UploadForm
from .parsers import safe_ecd_parse
from utils.converters import date_parser

from jira import JIRAError
from docxtpl import DocxTemplate
from io import BytesIO
from pathlib import Path
from base64 import b64decode, b64encode
import json
from enum import Enum
import requests
import re
import time
import uuid
from datetime import datetime
import os

try:
    import pandas as pd
except ImportError:
    pd = None

from bs4 import BeautifulSoup
from awcenter.enums import Projects

TEMPLATE_DIR = settings.CUSTOM_TEMPLATE_DIR
JIRA_URL = settings.JIRA_BTB_URL    

def check_filename(path, filename):
    for name in os.listdir(path):
        name = name.strip().replace("-", "").replace("–", "").replace(" ", "")
        print(path, name, filename)
        if filename in name:
            return True
    return False

def find_keyword_list2d(data, keyword):
    for row_index, row in enumerate(data):
        for col_index, item in enumerate(row):
            if keyword == item:
                return (row_index, col_index)  
    return None

def check_panel_text(metin):
    pattern = r"\b\d+[.:]"
    return bool(re.search(pattern, metin))

def extract_text_from_text(text, search_text1="", search_text2=""):
    if search_text1 == "":
        end_point = text.find(search_text2) 
        result = text[:end_point]
    elif search_text2 == "":
        end_point = len(text)
        result = text[text.find(search_text1) + len(search_text1):end_point]
    else:
        start_point = text.find(search_text1) + len(search_text1)
        end_point = text.find(search_text2, start_point)
        result = text[start_point:end_point]

    return result

def make_surname_upper(fullname):
    words = fullname.split()
    if not words:
        return fullname
    words[-1] = words[-1].upper()
    return ' '.join(words)

def parse_labels(text: str):
    if not text:
        return []
    
    labels = [l.strip() for l in text.split(";") if l.strip()]
    
    labels = [
        l.lower().replace(" ", "_")
        for l in labels
    ]
    
    return labels

def parse_multiselect(text: str):
    if not text:
        return []
    
    items = []
    seen = set()
    
    for part in text.split(";"):
        value = part.strip()
        if not value:
            continue
        
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        
        items.append({"value": value})
        
    return items

def multiselect_to_text(values) -> str:
    if not values:
        return ""

    # Tek obje geldiyse listeye çevir
    if not isinstance(values, (list, tuple, set)):
        values = [values]

    result = []

    for item in values:
        if item is None:
            continue

        # dict formatı
        if isinstance(item, dict):
            value = item.get("value")
            if value:
                result.append(str(value).strip())
            continue

        # jira.resources.CustomFieldOption benzeri obje
        value = getattr(item, "value", None)
        if value:
            result.append(str(value).strip())
            continue

        # fallback: string ise direkt al
        if isinstance(item, str):
            item = item.strip()
            if item:
                result.append(item)

    return ", ".join(result)

def classify_dcc(classification_list):
    priority_map = {
        "Major": 1,
        "Minor-Additional Work": 2,
        "Minor-No Effect": 3
    }

    dominant = None
    for classification in classification_list:
        priority = priority_map.get(classification[0], None)
        if priority:
            if dominant is None or priority < priority_map[dominant[0]]:
                dominant = classification
    
    if dominant:
        return dominant[0], dominant[1]
    return None, None




@permission_classes([IsOwner])
class JIRA_DCC_ViewSet(APIView):
    def get(self, request, pk=None):
        if pk:
            dcc = get_object_or_404(JIRA_DCC, pk=pk)
            serializer = JIRA_DCC_Serializer(dcc)
            return Response(serializer.data)
        dccs = JIRA_DCC.objects.filter(created_by=request.user)
        #dccs = JIRA_DCC.objects.all()
        serializer = JIRA_DCC_Serializer(dccs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = JIRA_DCC_Serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        dcc = get_object_or_404(JIRA_DCC, pk=pk)
        serializer = JIRA_DCC_Serializer(dcc, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        dcc = get_object_or_404(JIRA_DCC, pk=pk)
        serializer = JIRA_DCC_Serializer(dcc, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        dcc = get_object_or_404(JIRA_DCC, pk=pk)
        serializer = JIRA_DCC_Serializer(dcc)
        dcc.delete()
        return Response(serializer.data, status=status.HTTP_204_NO_CONTENT)

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

def event_stream():
    for i in range(101):
        time.sleep(0.1)
        yield f'data: {json.dumps({"status": "Processing", "percentage": i})}\n\n'

def sse_test(request):
    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no" #nginx için
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_issue_list(request):
    issues = JIRA_DCC.objects.values("issue")
    return Response(issues)

@api_view(["POST"])
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def create_issue(request):
    try:
        data = request.data
        session_id = data.get("JSESSIONID", None)
        
        if session_id is None:
            return Response({"message": "No session ID found."}, status=400)
        
        _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=session_id)
        
        if _jira is None:
            return Response({"message": "Client error while connecting."}, status=400)
        
        try:
            project = Projects.from_jira_component(data.get("project"))
        except ValueError as e:
            return Response({"message": "Unsupported project."})
        
        issue_fields = {
            "project": "CHN",
            'summary': data["ecd_title"],
            "description": data["ecd_title"],
            'issuetype': {'name': 'Task'},
            "components": [{"name": project.jira_component}],
            "customfield_13054": [{"name": data["requestor"]}], #customfield_10768
            'customfield_45000': data["ecd_no"].split("/")[0].strip(), #customfield_13712
            'customfield_45001': data["ecd_no"].split("/")[1].strip(), #customfield_14297
            'customfield_45002': f"DCC - {project.dcc_label} - {str(datetime.now().year)} - XXX", #customfield_21271
            'customfield_34115': parse_multiselect(data["effectivity"]),
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

@api_view(["POST"])
def upload_ecd(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            ecd_file = request.FILES["file"]
            ecd_parsed = safe_ecd_parse(ecd_file)
            return Response(ecd_parsed)
        except Exception as e:
            return Response({"message": f"Something went wrong: {e}"}, 400)

    return Response({"message": "Can not parse ECR."}, status=400)
        

@api_view(["POST"])
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
def send_mail(request):
    try:
        data = request.data
        
        if data["JSESSIONID"]:
            _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
        else:
            return Response({"message": "JSESSIONID not found in request."}, status=400)
        
        _jira.set_issue(data["issue"])
        ccb_no = str(data["ccb_no"])
        due_date = data["due_date"]

        issue = _jira.get_issue()
        issue_f = issue.fields

        project = None
        for c in issue_f.components:
            try:
                project = Projects.from_jira_component(c.name)
            except ValueError as e:
                continue

        if project == None:
            return Response({"message": "Error while detecting project"}, status=400)

        cc_list = ""
        raw_dcc_path = ""
        html_file_path = ""
            
        mail_placeholder = {
            "{{ECD_NAME}}": issue_f.summary,
            "{{ECD_NO}}": f"{issue_f.customfield_45000} / {issue_f.customfield_45001}",
            "{{JIRA_LINK_NAME}}": _jira.get_issue_key(),
            "{{JIRA_LINK}}": f"{JIRA_URL}/browse/{_jira.get_issue_key()}",
            "{{DCC_PATH_NAME}}": issue_f.customfield_45002,
            "{{CCB_NO}}": ccb_no,
            "{{DUE_DATE}}": due_date,
        }
        
        html_file_path = TEMPLATE_DIR / project.mail_jira_template_name

        if project == Projects.HYS:
            raw_dcc_path = r"\\vds\projects\Prj300\14-Uçuşa_Elverişlilik_ve_Sertifikasyon\08_Design Change Management\02-ECD Takip\Design Change Classification Forms\2025"
            cc_list = "orcunozan.afsar@tai.com.tr; kemalbahadir.potuk1@tai.com.tr"
            mail_placeholder["{{DCC_PATH}}"] = f"{raw_dcc_path}\\{issue_f.customfield_45002}"
            mail_title = f"[HYS] CCB-{ccb_no} toplantı gündemi"
        elif project == Projects.OZGUR:
            raw_dcc_path = r"\\vds\projects\Prj071\Sertifikasyon\08-Design Change Management\02-ECD Takip Arch\Design Change Classification Forms\2025"
            cc_list = "mustafaalp.eren@tai.com.tr; kemalbahadir.potuk1@tai.com.tr"
            mail_placeholder["{{DCC_PATH}}"] = f"{raw_dcc_path}\\{issue_f.customfield_45002} ({issue_f.customfield_45000} {issue_f.customfield_45001})"
            mail_title = f"[Ozgur] CCB-{ccb_no} toplantı gündemi"
        else:
            return Response({"message": "Something went wrong, not supported project. Process stopped."}, status=400)

        open_subtask_list = _jira.get_open_subtask()
        to_list = ';'.join([open_subtask.fields.assignee.emailAddress for open_subtask in open_subtask_list])

        content = html_to_text(html_file_path)
        content = replace_all_keys(content, mail_placeholder)

        SendMail(mail_title, content, to_list, cc_list)

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
@permission_classes([IsAuthenticated])
def add_attachment(request):
    print(request.data)
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            data = request.data
            
            file = data.get("file", None)
            
            if not file:
                return Response({"message": "File not found."}, status=400)
                
            _jira = JiraConnector(server_url=JIRA_URL, jira_session_id=data["JSESSIONID"])
            _jira.set_issue(data["issue_key"])
            _jira.add_attachment(file, filename=file.name)

            return Response({"message": f"Attachment named {file.name} added to {data['issue_key']}"}, status=201)
        except JIRAError as e:
            return Response({"message": f"Jira Error: {e.response.text}"}, status=400)
        except Exception as e:
            return Response({"message": f"Something went wrong while adding attachment: {e}"}, status=400)
        
    return Response({"message": "Form is not valid"}, status=400)

def create_subtask_action(uuid):
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
            if subtasks:
                percentage = 0
                step_size = int(100/len(subtasks))
                for subtask in subtasks:
                    yield f'data: {json.dumps({"status": "progress", "percentage": percentage, "content": subtask["summary"]})}\n\n'
                    _jira.create_subtask(summary=subtask["summary"], assignee=subtask["assignee"])
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
        


def create_subtask_stream(request, uuid):
    response = StreamingHttpResponse(create_subtask_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def create_subtask_excel_action(uuid):
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

            if pd is None:
                yield f'data: {json.dumps({"status": "error", "content": "pandas is required for excel import."})}\n\n'
                return

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



def create_subtask_excel_stream(request, uuid):
    response = StreamingHttpResponse(create_subtask_excel_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_session(request):
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
@permission_classes([IsAuthenticated])
def create_queue(request):
    file = request.FILES.get("file", None)
    data = {}
    if file:
        data["file"] = file.read()
        data["parameters"] = request.data.get("parameters", None)
    else:
        data = request.data
        
    new_uuid = str(uuid.uuid4())
    cache.set(new_uuid, data)
    return Response(new_uuid)

def create_dcc_action(uuid):
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

            loader_percentage = 0
            yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": loader_percentage, "content": "Analyzing..."})}\n\n'

            issue = _jira.get_issue()
            if issue == None:
                yield f'data: {json.dumps({"status": "error", "type": "text", "content": "Task not found."})}\n\n'
                return
            issue_f = issue.fields

            if issue_f.issuetype.subtask == True:
                yield f'data: {json.dumps({"status": "error", "type": "text", "content": "A Subtask URL address was detected. Please enter a Task URL address!"})}\n\n'
                return

            project = None
            for c in issue_f.components:
                try:
                    project = Projects.from_jira_component(c.name)
                except ValueError as e:
                    continue
            
            if project is None:
                yield f'data: {json.dumps({"status": "error", "type": "text", "content": "Unsupported project."})}\n\n'
                return
            
            dcc_placeholder = {}

            loader_percentage += 20
            yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": loader_percentage, "content": f"[{project.jira_component}] {issue_f.summary}"})}\n\n'

            if issue_f.summary != None:
                dcc_placeholder["Design_Change_Title"] = issue_f.summary
            if issue_f.customfield_45002 != None:
                dcc_placeholder["DCC_Form_Number"] = issue_f.customfield_45002
            if issue_f.customfield_45000 != None:
                dcc_placeholder["Design_Change_Number"] = issue_f.customfield_45000
            if issue_f.customfield_45001 != None:
                dcc_placeholder["Design_Change_Revision"] = issue_f.customfield_45001
            if issue_f.customfield_13716 != None:
                dcc_placeholder["Design_Change_Classification"] = issue_f.customfield_13716.value
            if issue_f.updated != None:
                dcc_placeholder["Update_Time"] = datetime.today().strftime("%d.%m.%Y") # ISO_time_to_string(issue_f.updated)
            if issue_f.customfield_34115 != None:
                dcc_placeholder["Applicability"] = multiselect_to_text(issue_f.customfield_34115)

            if 'Design_Change_Number' in dcc_placeholder and 'Design_Change_Revision' in dcc_placeholder:
                dcc_placeholder["Design_Change_Name"] = f"{dcc_placeholder['Design_Change_Number']} / {dcc_placeholder['Design_Change_Revision']}"

            classification_list = []
            inc_size = int(60 / (1 if len(issue.fields.subtasks) == 0 else len(issue.fields.subtasks)))
            for index, subtask in enumerate(issue.fields.subtasks):
                s = _jira.get_client().issue(subtask.key)
                sf = s.fields
                dcc_placeholder[f"Panel_Status_{index+1}"] = sf.status.name
                clean_as_name = split_text_by_chracter(sf.assignee.displayName, "(")
                dcc_placeholder[f"Panel_AS_Name_{index+1}"] = make_surname_upper(clean_as_name)
                dcc_placeholder[f"Panel_Updated_Time_{index+1}"] = ISO_time_to_string(sf.updated)

                if sf.customfield_45006: #customfield_27271
                    dcc_placeholder[f"Affected_Requirements_{index+1}"] = sf.customfield_45006

                if sf.customfield_45007: #customfield_27174
                    dcc_placeholder[f"Further_Compliance_{index+1}"] = sf.customfield_45007

                if sf.customfield_45008:
                    dcc_placeholder[f"Design_Change_Assessment_{index+1}"] = sf.customfield_45008
                
                splitText = sf.summary.split("Panel")
                if len(splitText) == 2:
                    panel_name = splitText[0].strip()
                else:
                    panel_name = "this"
                    
                if project.dcc_label == "GJ":
                    if panel_name == "Flight" and clean_as_name != "Utku İnanç Pehlivan":
                        dcc_placeholder[f"Panel_AS_Name_{index+1}"] = f"Utku İnanç PEHLİVAN, {dcc_placeholder[f'Panel_AS_Name_{index+1}']}"
                    elif panel_name == "Human Factor" and clean_as_name != "Aslı Alpsoy":
                        dcc_placeholder[f"Panel_AS_Name_{index+1}"] = f"Aslı ALPSOY, {dcc_placeholder[f'Panel_AS_Name_{index+1}']}"
                    elif panel_name == "Electrical Systems/E3" and clean_as_name != "Merve Helvacı":
                        dcc_placeholder[f"Panel_AS_Name_{index+1}"] = f"Merve HELVACI, {dcc_placeholder[f'Panel_AS_Name_{index+1}']}"

                
                if sf.customfield_45004:
                    classification_list.append((sf.customfield_45004.value, sf.assignee))
                else:
                    classification_list.append(("Minor-No Effect", sf.assignee))

                comments = sf.comment.comments
                if issue_f.components[0].name == "Gökbey Jandarma" and comments:
                    soup = BeautifulSoup(comments[0].body, 'html.parser')

                    extracted_text = soup.get_text(separator='\n', strip=True).replace('\n', ' ')                
                    certification_change_classification = extract_text_from_text(extracted_text, "(According to GM 21.A.91): ", " Affected Requirements")
                    affected_requirements = extract_text_from_text(extracted_text, "Compliance Documents: ", " Further Compliance Study for Design Change:")
                    further_compliance_study = extract_text_from_text(extracted_text, " Further Compliance Study for Design Change: ", " Design Change Assessment:")
                    design_change_assessment = extract_text_from_text(extracted_text, " Design Change Assessment: ")

                    dcc_placeholder[f"Certification_Change_Classification_{index+1}"] = certification_change_classification
                    dcc_placeholder[f"Affected_Requirements_{index+1}"] = affected_requirements
                    dcc_placeholder[f"Further_Compliance_{index+1}"] = further_compliance_study
                    dcc_placeholder[f"Design_Change_Assessment_{index+1}"] = design_change_assessment

                    classification_list.append((certification_change_classification, sf.assignee))

                loader_percentage += inc_size
                yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": loader_percentage, "content": f"{sf.summary} - {sf.status.name}"})}\n\n'

            classified_type, responsible_as = classify_dcc(classification_list)
            if classified_type and not "Design_Change_Classification" in dcc_placeholder :
                dcc_placeholder["Design_Change_Classification"] = classified_type
            
            if sf.customfield_45005 is not None:
                dcc_placeholder["Responsible_AS"] = sf.customfield_45005
            elif responsible_as:
                dcc_placeholder["Responsible_AS"] = make_surname_upper(split_text_by_chracter(responsible_as.displayName, "("))

            
            d = DocxTemplate(TEMPLATE_DIR / project.dcc_template_name)

            loader_percentage = 80
            save_name = f"{dcc_placeholder.get('DCC_Form_Number', 'DCC')}.docx"
            yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": loader_percentage, "content": f"Creating {save_name}"})}\n\n'
            d.render(dcc_placeholder)
            buffer = BytesIO()
            d.save(buffer)
            buffer.seek(0)
            yield f'data: {json.dumps({"status": "progress", "type": "loader", "percentage": 100, "content": f"DCC created: {save_name}"})}\n\n'
            encoded = b64encode(buffer.read()).decode()
            yield f'data: {json.dumps({"status": "success", "content": encoded, "filename": save_name})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"status": "error", "type": "text", "content": str(e)})}\n\n'
    else:
        yield f'data: {json.dumps({"status": "error", "content": f"UUID not in the queue: {uuid}"})}\n\n'

def create_dcc_stream(request, uuid):
    response = StreamingHttpResponse(create_dcc_action(str(uuid)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
