from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from base64 import b64decode, b64encode
from django.conf import settings
from requests.exceptions import ConnectionError, Timeout, HTTPError, RequestException

import requests
import os
import json

CERTIFICATE_FILE = settings.CERTIFICATES_DIR / "dmntai_intra.crt"
DOCPROOF_URL = settings.DOCPROOF_URL

# Login
session = requests.Session()
session.verify = CERTIFICATE_FILE if CERTIFICATE_FILE.exists() else False
url = f"{DOCPROOF_URL}/j_spring_security_check"

aw_username = settings.AW_USERNAME
aw_password = settings.AW_PASSWORD

if aw_username and aw_password:
    value_1 = b64decode(aw_username).decode("utf-8")
    value_2 = b64decode(aw_password).decode("utf-8")
    payload = {
        "j_username": value_1,
        "j_password": value_2,
    }

def login():
    try:
        res = session.post(url, data=payload, timeout=5)
        res.raise_for_status()
    except ConnectionError as e:
        print(f"Server error while connecting to Docproof: {e}")
    except Timeout as e:
        print(f"Connection timeout while connecting to Docproof: {e}")
    except HTTPError as e:
        print(f"HTTP error while connecting to Docproof: {e}")
    except RequestException as e:
        print(f"General request error while connecting to Docproof: {e}")
    except Exception as e:
        print(f"Unexpected error while connecting to Docproof: {e}")
        
login()
#for cookie in session.cookies:
#    print(f"{cookie.name} = {cookie.value}")

@api_view(["GET"])
@permission_classes([AllowAny])
def test(request):
    return Response("DOCPROOF SUCCESS")

@api_view(["GET"])
@permission_classes([AllowAny])
def search(request):
    document_no = request.query_params.get("document_no", None)

    if not document_no:
        return Response({"detail": "Document number required."}, status=400)

    document_no = document_no.split("/")[0]
    

    try:
        search_result_raw = session.get(f"{DOCPROOF_URL}/realtime-queries/dprf_search_proof_readin?inline=true&input_document_number={document_no}")
        search_result_raw.raise_for_status()
        search_result = search_result_raw.json()
        total = search_result["total"]
        if total <= 0:
            return Response({"message": f"Can not find or access document: {document_no}"}, status=400)

        object_id = None
        pr_no = 0
        for entry in reversed(search_result["entries"]):
            if entry["content"]["properties"]["pr_status"] == "EDMS" and pr_no < entry["content"]["properties"]["pr_no"]:
                pr_no = entry["content"]["properties"]["pr_no"]
                object_id = entry["content"]["properties"]["id"]
        if not object_id:
            return Response({"message": f"Can not find published document in EDMS: {document_no}"}, status=400)
        
        doc_object_raw = session.get(f"{DOCPROOF_URL}/folders/dprf_proof_reading/{object_id}/objects?inline=true")
        doc_object = doc_object_raw.json()
        
        issue_no = 0
        for entry in doc_object["entries"]:
            if (entry["content"]["type"] == "dprf_technical_document" or entry["content"]["type"] == "dprf_cdcp_document"):
                issue_no = entry["content"]["properties"]["issue"]
                break
        
        return Response(issue_no, status=200)
    except requests.exceptions.HTTPError as e:
        print("Trying login DocProof again...")
        login()
    except Exception as e:
        print(f"Something went wrong: {e}")
        return Response(f"Something went wrong: {e}", status=400)


    return