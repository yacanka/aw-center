"""Copy content before retiring its old preference fields."""

from django.db import migrations
from django.db.models import JSONField, Value


def copy_content(apps, schema_editor):
    alias = schema_editor.connection.alias
    Preferences = apps.get_model("users", "UserPreferences")
    JiraContent = apps.get_model("integrations", "JiraUserContent")
    AnalysisContent = apps.get_model("word", "DocumentAnalysisUserContent")
    for preferences in Preferences.objects.using(alias).iterator():
        # A JSON null must stay JSON null, rather than becoming SQL NULL.
        JiraContent.objects.using(alias).create(user_id=preferences.user_id,
            subtask_lists=Value(preferences.jira_list, output_field=JSONField()))
        AnalysisContent.objects.using(alias).create(user_id=preferences.user_id,
            checks=Value(preferences.document_analysis_checks, output_field=JSONField()))


class Migration(migrations.Migration):
    dependencies = [("users", "0002_userpreferences_version"),
                    ("integrations", "0003_jirausercontent"), ("word", "0001_initial")]
    operations = [migrations.RunPython(copy_content, migrations.RunPython.noop)]
