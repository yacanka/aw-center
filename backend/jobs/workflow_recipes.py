"""Allowlisted workflow recipes exposed to authenticated users."""

from dataclasses import dataclass

from rest_framework.exceptions import ValidationError

from awcenter.file_security import MSG_POLICY, WORD_DOCUMENT_POLICY, UploadPolicy
from word.job_executor import SUPPORTED_TRANSLATIONS


@dataclass(frozen=True)
class WorkflowStepDefinition:
    """Describe one immutable step in a workflow recipe."""

    sequence: int
    kind: str
    label: str
    handoff_id: str = ""


@dataclass(frozen=True)
class WorkflowRecipe:
    """Describe one safe server-owned multi-step automation."""

    identifier: str
    title: str
    description: str
    input_label: str
    input_help: str
    upload_policy: UploadPolicy
    steps: tuple[WorkflowStepDefinition, ...]
    parameters: tuple[dict, ...] = ()


TRANSLATION_FIELD = {
    "name": "translate_type",
    "label": "Translation direction",
    "type": "select",
    "required": True,
    "options": (
        {"value": "tr2en", "label": "Turkish → English"},
        {"value": "en2tr", "label": "English → Turkish"},
    ),
}


TRANSLATE_AND_ANALYZE = WorkflowRecipe(
    identifier="translate-and-analyze",
    title="Translate and analyze a Word document",
    description="Translate once, then automatically run explainable compliance checks.",
    input_label="Word document",
    input_help="The original and generated documents remain in private storage.",
    upload_policy=WORD_DOCUMENT_POLICY,
    steps=(
        WorkflowStepDefinition(1, "word.translate", "Translate document"),
        WorkflowStepDefinition(
            2, "word.analyze", "Analyze translated document", "analyze-translated-document"
        ),
    ),
    parameters=(TRANSLATION_FIELD,),
)
ANALYZE_OUTLOOK_ATTACHMENT = WorkflowRecipe(
    identifier="analyze-outlook-word-attachment",
    title="Analyze a Word attachment from Outlook",
    description="Extract the only DOCX attachment from a MSG file and analyze it automatically.",
    input_label="Outlook message",
    input_help="Messages with zero or multiple Word attachments stop with an actionable error.",
    upload_policy=MSG_POLICY,
    steps=(
        WorkflowStepDefinition(
            1, "outlook.extract_word_attachment", "Extract Word attachment"
        ),
        WorkflowStepDefinition(
            2, "word.analyze", "Analyze Word attachment", "analyze-outlook-word-attachment"
        ),
    ),
)
WORKFLOW_RECIPES = {
    recipe.identifier: recipe
    for recipe in (TRANSLATE_AND_ANALYZE, ANALYZE_OUTLOOK_ATTACHMENT)
}


def get_workflow_recipe(identifier):
    """Return one allowlisted workflow recipe or reject the identifier."""

    recipe = WORKFLOW_RECIPES.get(str(identifier or ""))
    if not recipe:
        raise ValidationError({"recipe": "Select a supported workflow recipe."})
    return recipe


def validate_workflow_parameters(recipe, parameters):
    """Validate and normalize parameters for one workflow recipe."""

    if recipe.identifier == ANALYZE_OUTLOOK_ATTACHMENT.identifier:
        return {}
    if recipe.identifier != TRANSLATE_AND_ANALYZE.identifier:
        raise ValidationError({"recipe": "This workflow recipe is not executable."})
    translation_type = str(parameters.get("translate_type") or "").lower()
    if translation_type not in SUPPORTED_TRANSLATIONS:
        raise ValidationError({"translate_type": "Select a supported translation direction."})
    return {"translate_type": translation_type}


def workflow_recipe_catalog():
    """Return UI-safe metadata for every available recipe."""

    return [serialize_recipe(recipe) for recipe in WORKFLOW_RECIPES.values()]


def serialize_recipe(recipe):
    """Serialize one recipe without exposing implementation callbacks."""

    return {
        "id": recipe.identifier,
        "title": recipe.title,
        "description": recipe.description,
        "input": {
            "label": recipe.input_label,
            "help": recipe.input_help,
            "accept": sorted(recipe.upload_policy.extensions),
        },
        "steps": [
            {"sequence": step.sequence, "kind": step.kind, "label": step.label}
            for step in recipe.steps
        ],
        "parameters": list(recipe.parameters),
    }
