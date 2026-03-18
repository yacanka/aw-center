from __future__ import annotations
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

from pathlib import Path
import extract_msg, io, base64, mimetypes, re, json
from typing import Any, Dict, List, Tuple

SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

def _safe_filename(name: str) -> str:
    name = (name or "attachment").strip().replace("\0", "")
    name = SAFE_NAME_RE.sub("_", name)
    return name[:255] or "unnamed"

def _pick_name(att) -> str:
    return getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "attachment"

def _msg_to_dict(msg: extract_msg.Message) -> Dict[str, Any]:
    # basit alanlar
    d = {
        "subject": msg.subject,
        "sender": msg.sender,         # "Ad <mail@...>" gibi
        "to": msg.to,                 # virgüllü
        "cc": msg.cc,
        "bcc": msg.bcc,
        "date": msg.date,             # string döner
        "body_plain": msg.body,       # varsa düz metin
        "body_html": None,
    }
    # html body elde etmeyi deneyelim (bazı maillerde yok)
    try:
        d["body_html"] = getattr(msg, "htmlBody", None)
    except Exception:
        d["body_html"] = None
    return d

class MsgParseView(APIView):
    """
    POST multipart/form-data:
      - file: .msg
      - inline: "true"/"false"  (ekleri base64 ile JSON içinde dönsün mü?)
    Dönüş:
      {
        "mail": {...},
        "attachments": [
          {
            "name": "foo.pdf",
            "size": 12345,
            "mime": "application/pdf",
            # inline=true ise:
            "content_base64": "JVBERi0xLjcK..."
            # inline=false ise:
            "download_url": "/api/msg/download?token=...&index=0"
          }, ...
        ],
        "token": "...."  # inline=false ise verilir (indirme için)
      }
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "file alanı gerekli (.msg yükleyin)."}, status=400)

        inline = str(request.POST.get("inline", "false")).lower() == "true"
        try:
            # extract_msg Message(), dosya yolunu ister; BytesIO ile de çalışır:
            bio = io.BytesIO(f.read())
            msg = extract_msg.Message(bio)
        except Exception as e:
            return Response({"detail": f".msg okunamadı: {e}"}, status=400)

        mail_info = _msg_to_dict(msg)

        # ekler
        atts_meta: List[Dict[str, Any]] = []
        attachments_bytes: List[bytes] = []

        for att in msg.attachments:
            name = _safe_filename(_pick_name(att))
            data: bytes = getattr(att, "data", b"")
            if not isinstance(data, (bytes, bytearray)):
                try:
                    data = bytes(data)
                except Exception:
                    data = b""
            size = len(data)
            mime, _ = mimetypes.guess_type(name)
            mime = mime or "application/octet-stream"

            attachments_bytes.append(bytes(data))
            atts_meta.append({
                "name": name,
                "size": size,
                "mime": mime,
            })

        if inline:
            # küçük ekler/rapid prototipleme için: base64 dön
            for i, meta in enumerate(atts_meta):
                meta["content_base64"] = base64.b64encode(attachments_bytes[i]).decode("ascii")
            payload = {"mail": mail_info, "attachments": atts_meta}
            return Response(payload, status=status.HTTP_200_OK)
        else:
            # üretim: cache’e koy, token üret, indirecek endpoint ver
            token = get_random_string(32)
            # cache’e meta + bytes koyuyoruz (prod’da Redis/Memcached önerilir)
            cache.set(f"MSG:{token}", {
                "attachments": [
                    {"name": m["name"], "mime": m["mime"], "bytes": attachments_bytes[i]}
                    for i, m in enumerate(atts_meta)
                ]
            }, timeout=60*30)  # 30 dk

            # istemciye download_url’leri hazır verelim
            for i, meta in enumerate(atts_meta):
                meta["download_url"] = f"/outlook/msg/download?token={token}&index={i}"

            payload = {"mail": mail_info, "attachments": atts_meta, "token": token}
            return Response(payload, status=status.HTTP_200_OK)

@permission_classes([AllowAny])
class MsgDownloadAttachmentView(APIView):
    """
    GET /api/msg/download?token=...&index=0
    Bellekten stream ederek ek indirir (diske yazmaz).
    """
    def get(self, request, *args, **kwargs):
        token = request.GET.get("token")
        index_str = request.GET.get("index")
        if not token or index_str is None:
            return HttpResponseBadRequest("token ve index gerekli.")

        try:
            idx = int(index_str)
        except ValueError:
            return HttpResponseBadRequest("index sayısal olmalı.")

        pack = cache.get(f"MSG:{token}")
        if not pack:
            return HttpResponse(status=404)

        atts = pack.get("attachments", [])
        if idx < 0 or idx >= len(atts):
            return HttpResponse(status=404)

        item = atts[idx]
        data: bytes = item["bytes"]
        name: str = _safe_filename(item["name"])
        mime: str = item.get("mime") or "application/octet-stream"

        resp = HttpResponse(data, content_type=mime)
        resp["Content-Length"] = str(len(data))
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp


