from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0008_userinvitation")]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="document_analysis_checks",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
