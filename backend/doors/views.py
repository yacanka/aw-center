from django.shortcuts import render
from django import forms
from django.conf import settings

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView 
from rest_framework import status

try:
    import pythoncom
except ImportError:
    pythoncom = None
import pandas as pd
import json

import os
from base64 import b64decode
from utils.process import get_or_run
from .dxl_library import get_ata_chapter_check, get_req_poc_linker


AW_USERNAME = settings.AW_USERNAME
AW_PASSWORD = settings.AW_PASSWORD
DOORS_PATH = settings.DOORS_EXECUTABLE
DOORS_PARAMS = ["-u", b64decode(AW_USERNAME).decode("utf-8"), "-P", b64decode(AW_PASSWORD).decode("utf-8")]
DXL_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "doors_dxl_output.log")


class UploadForm(forms.Form):
    file = forms.FileField()



def get_doors_process():
    return get_or_run("DOORS.Application", DOORS_PATH, DOORS_PARAMS)

@api_view(["GET"])
@permission_classes([AllowAny])
def test(request):
    return Response("HELP")

@api_view(["POST"])
def run_dxl(request):
    mode = request.data["mode"]

    if mode == "ata_chapter_check":
        module_path = request.data["module_path"]
        dxl_code = get_ata_chapter_check(module_path)
    elif mode == "req_poc_linker":
        ref_module_name = request.data["ref_module_name"]
        link_module_name = request.data["link_module_name"]
        target_module_name = request.data["target_module_name"]
        ref_attr_poc = request.data["ref_attr_poc"]
        ref_attr_req = request.data["ref_attr_req"]
        target_attr_poc = request.data["target_attr_poc"]
        start_index = request.data["start_index"]
        text_length = request.data["text_length"]
        direction = request.data["direction"]
        activeness = request.data["activeness"]
        
        dxl_code = get_req_poc_linker(ref_module_name, link_module_name, target_module_name, ref_attr_poc, ref_attr_req, target_attr_poc, start_index, text_length, direction, activeness)
    try:
        if pythoncom is None:
            return Response({"detail": "DOORS automation is not available on this environment."}, status=400)

        pythoncom.CoInitialize()
        doors = get_doors_process()
        #doors = win32com.client.Dispatch("DOORS.Application")
        #doors = win32com.client.gencache.EnsureDispatch("DOORS.Application")
        
        if doors:
            result = doors.runStr(dxl_code)
        
        if os.path.exists(DXL_OUTPUT_PATH):
            with open(DXL_OUTPUT_PATH, "r") as file:
                lines = file.read()
                return Response(lines, status=200)
        else:
            return Response({"detail": "No doors output found."}, status=400)
    except Exception as e:
        return Response({"detail": f"Error while connecting DOORS: {e}"}, status=400)

@api_view(["POST"])
def create_script(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            excel_file = request.FILES["file"]
            data = json.loads(request.POST["json"])

            target_index = next((i for i, item in enumerate(data) if item["search"] == True), None)
            if target_index is not None:
                data.insert(0, data.pop(target_index))

            excel_column_names = [item["excel"] for item in data]
            df = pd.read_excel(excel_file)

            length = len(df)
            arrays = []
            for column_name in excel_column_names:
                array = []
                for index, row in df.iterrows():
                    if pd.isna(row[column_name]):
                        array.append('""')
                    else:
                        text = str(row[column_name]).strip().replace("\"", "\'")
                        array.append(f'"{text}"')
                arrays.append(array)

            arrays_text = "\n".join([f"string arr{i+1}[] = {{{','.join(array)}}}" for i, array in enumerate(arrays)])
            set_attribute_text = "\n\t".join([f"SetObjectAttribute(o, \"{item['doors']}\", arr{i+1}[i])" for i, item in enumerate(data[1:], start=1)])

            dxl_script = f'''
#include <addins/user/yck.dxl>

Module refModule = current
if (null refModule ) {{
	print "Module not found\\n"
	halt
}}

{arrays_text}

Object o
int i = 0
for (i = 0; i < {length}; i++){{
    o = FindObjectByAttribute(refModule, "{data[0]['doors']}", arr1[i])
    if (null o) {{
		print "Object not found: " arr1[i] "\\n"
	}}
    else {{
        //print o.("{data[0]['doors']}") "\\n"
        {set_attribute_text}
    }}
}}
'''

            return Response(dxl_script)
        except Exception as e:
            return Response(f"Error while creating script: {e}", status=400)
    
    return Response("Not a valid form.")
