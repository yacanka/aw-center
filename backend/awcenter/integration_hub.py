"""Non-secret capability catalog for AW Center integration bridges."""

import importlib.util
import shutil
import sys
from pathlib import Path

from django.conf import settings

from doors.services import integration_status as doors_status
from teamcenter.services import integration_status as teamcenter_status


def integration_catalog():
    """Return configuration readiness for supported integration bridges."""

    return [
        _jira_integration(),
        _teamcenter_integration(),
        _doors_integration(),
        _docproof_integration(),
        _office_integration(),
        _ai_integration(),
        _media_integration(),
    ]


def _jira_integration():
    return _item(
        "jira",
        "JIRA",
        bool(settings.JIRA_BTB_URL),
        "Change control, issue creation, subtasks, attachments and traceability.",
        ["change-control", "issues", "attachments", "workflow"],
        "/dcc",
    )


def _teamcenter_integration():
    status = teamcenter_status()
    return _item(
        "teamcenter",
        "Teamcenter",
        bool(status["configured"]),
        "PLM saved queries, object properties and controlled updates.",
        ["plm", "saved-queries", "objects", "properties"],
        "/teamcenter/agent",
    )


def _doors_integration():
    status = doors_status()
    ready = bool(status["configured"] and status["platform_supported"])
    return _item(
        "doors",
        "IBM Rational DOORS",
        ready,
        "Requirements modules, object discovery and controlled DXL automation.",
        ["requirements", "dxl", "objects", "traceability"],
        "/doors/agent",
        configured=bool(status["configured"]),
    )


def _docproof_integration():
    configured = all(
        [settings.DOCPROOF_URL, settings.AW_USERNAME, settings.AW_PASSWORD]
    )
    return _item(
        "docproof",
        "DocProof",
        configured,
        "Published document issue lookup for compliance workflows.",
        ["documents", "published-issue", "compliance"],
        None,
    )


def _office_integration():
    packages = ("openpyxl", "docx", "pypdf", "extract_msg")
    ready = all(importlib.util.find_spec(package) for package in packages)
    return _item(
        "office",
        "Office Document Toolkit",
        ready,
        "Excel, Word, PDF and Outlook parsing, comparison and generation.",
        ["excel", "word", "pdf", "outlook"],
        "/compare/excel",
    )


def _media_integration():
    executable = settings.FFMPEG_EXECUTABLE
    ready = bool(shutil.which(executable) or Path(executable).is_file())
    return _item(
        "media",
        "Media Toolkit",
        ready,
        "Bounded FFmpeg conversion and output-size estimation.",
        ["video", "audio", "images", "conversion"],
        "/media-converter",
    )


def _ai_integration():
    models = (
        settings.WORD_TRANSLATION_TR_EN_MODEL,
        settings.WORD_TRANSLATION_EN_TR_MODEL,
        settings.WORD_ANALYZER_BI_MODEL,
        settings.WORD_ANALYZER_CROSS_MODEL,
    )
    runtimes = ("transformers", "sentence_transformers")
    ready = all(importlib.util.find_spec(runtime) for runtime in runtimes) and all(
        Path(model).is_dir() for model in models
    )
    return _item(
        "ai",
        "Local AI Toolkit",
        ready,
        "Private local-model Word translation and explainable compliance analysis.",
        ["translation", "document-analysis", "local-models", "document-privacy"],
        "/translator",
    )


def _item(identifier, name, ready, description, capabilities, route, configured=None):
    return {
        "id": identifier,
        "name": name,
        "category": "external" if identifier not in {"office", "media", "ai"} else "local",
        "status": "ready" if ready else "attention",
        "configured": ready if configured is None else configured,
        "description": description,
        "capabilities": capabilities,
        "route": route,
        "platform": "windows" if sys.platform == "win32" else "cross-platform",
    }
