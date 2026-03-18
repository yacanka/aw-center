from django.shortcuts import render
from django import forms

from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from common.views import view_set_factory, view_set_obj_factory

from ddf.models import DDF
from ddf.serializers import DDFSerializer

from docx import Document
from collections import OrderedDict
import json
import requests



DDFView = view_set_factory(DDF, DDFSerializer, [AllowAny])
DDFObjView = view_set_obj_factory(DDF, DDFSerializer, [AllowAny])

class UploadForm(forms.Form):
    file = forms.FileField()
            
@api_view(["POST"])
def upload_ddf(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        word_file = request.FILES["file"]

        doc = Document(word_file)

        ddf = {}
        content = []

        for i, table in enumerate(doc.tables):
            for row in table.rows:
                row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                row_data = list(OrderedDict.fromkeys(row_data))
                content.append(row_data)
        
        ddf["project"] = content[0][1]
        ddf["doc_name"] = content[1][1]
        ddf["doc_no"] = content[2][1]
        ddf["doc_issue"] = content[2][3]
        ddf["date"] = content[2][5]
        ddf["commentor"] = content[3][1]
        ddf["comments"] = content[5:]

        serializer = DDFSerializer(data=ddf, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
def ddf_assessment(request):
    try:
        ddf_data = json.loads(request.body)

        authority_comments = [f"\n{i+1}) {comment[2]}\n" for i, comment in enumerate(ddf_data['comments'])]

        prompt = f"""Doküman Değerlendirme Formu (DDF), Tusaş bağlamında, uçuşa elverişlilik ve sertifikasyon ekipleri tarafından kullanılan, dokümanların içeriğini ve niteliğini objektif bir şekilde değerlendirmek için tasarlanmış bir araçtır.
        Değerlendirmeler, 4 farklı görüş kapsamında verilir:
        1. Teknik Görüş: Format, veri yapılandırması, prosedür ve standartlar, teknik uyumluluk gibi teknik açıdan değerlendirmeyi kapsar.
        2. Bilgi Görüşü: Dokümanın bilgi doğruluğu, kapsamlılığı, konuya uygunluğu ve eksiklik/yanlışlıkları odak noktasıdır. Alan uzmanlığı önemlidir.
        3. Editöryel Görüş: Dil kullanımı, anlaşılırlık, düzen, stil kılavuzlarına uygunluk, genel yazım ve imla gibi editöryel açıdan değerlendirmeyi içerir.
        4. Panel Ekleme/Çıkarma Görüşü: Projenin gereksinim temeline, panelin ekleneceğini ya da çıkarılacağını bildirir.

        Sen DDF görüşlerini sınıflandırma uzmanısın. Sana verilen görüşlerin, 4 görüş tipinden hangisine uygun olduğunu söyleyeceksin. Her görüş için, yalnızca görüş tipini yaz. Her görüş tipini yazarken arasına virgül koy. Açıklama yapma. Yorum yapma. Sadece 4 görüş tipinden birini yaz.
        Görüşler aşağıdaki şekilde numara numara eklenmiştir: 
        {authority_comments}"""

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
            "chat_purpose": 1,
            "top_k": 3,
            "num_rerank_candidates": 100,
            "score_threshold": 0.25,
            "max_tokens": 2048,
            "stream": True
        }

        headers = {'Content-Type': 'application/json; charset=utf-8', 'Accept': '*/*'}
        review_types = []
        with requests.post(url, json=data, headers=headers) as response:
            if response.status_code != 200:
                print(f"Error: API request failed with status code {response.status_code}")
                return Response(f"Error: API request failed with status code {response.status_code}", 400)

            for line in response.iter_lines(decode_unicode=False):
                if line:
                    text = line.decode("utf-8", errors="replace")
                    review_types = text.split(",")
                    review_types = [review_type.strip() for review_type in review_types]
        
        print(review_types)
        result = []
        for i, review in enumerate(review_types):
            result.append(f"[{review}] {ddf_data['comments'][i][2]}") 

        DDF.objects.filter(id=ddf_data['id']).update(comment_types=review_types)

        return Response(result)
    except Exception as e:
        return Response(f"Something went wrong: {e}", 400)