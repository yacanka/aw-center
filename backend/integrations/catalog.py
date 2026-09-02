"""Non-secret capability catalog for AW Center integrations."""

import importlib.util
import shutil
from pathlib import Path

from django.conf import settings

from automations.runner_protocol import runner_status
from integrations.teamcenter.services import integration_status as teamcenter_status


def integration_catalog():
    """Return configuration readiness for supported integrations."""

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
    configured = bool(settings.JIRA_ENABLED and settings.JIRA_URL)
    return _item(
        "jira",
        "JIRA",
        configured,
        "Change control, issue creation, subtasks, attachments and traceability.",
        ["change-control", "issues", "attachments", "workflow"],
        "/dcc",
    )


def _teamcenter_integration():
    status = teamcenter_status()
    configured = bool(
        settings.TEAMCENTER_ENABLED
        and settings.TEAMCENTER_BASE_URL
        and status["configured"]
    )
    return _item(
        "teamcenter",
        "Teamcenter",
        configured,
        "PLM saved queries, object properties and controlled updates.",
        ["plm", "saved-queries", "objects", "properties"],
        "/teamcenter/agent",
    )


def _doors_integration():
    status = runner_status()
    ready = bool(settings.DOORS_ENABLED and status["available"])
    return _item(
        "doors",
        "IBM Rational DOORS",
        ready,
        "Requirements modules, object discovery and controlled DXL automation.",
        ["requirements", "dxl", "objects", "traceability"],
        "/doors/agent",
        configured=bool(settings.DOORS_ENABLED and status["configured"]),
    )


def _docproof_integration():
    configured = all(
        [
            settings.DOCPROOF_ENABLED,
            settings.DOCPROOF_URL,
            settings.DOCPROOF_USERNAME,
            settings.DOCPROOF_PASSWORD,
        ]
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
        "platform": "windows" if identifier == "doors" else "cross-platform",
    }
