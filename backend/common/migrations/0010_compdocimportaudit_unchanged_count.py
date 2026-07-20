from django.db import migrations, models


class Migration(migrations.Migration):
    """Persist no-op rows in compliance-document import evidence."""

    dependencies = [("common", "0009_actioncenterdecision")]

    operations = [
        migrations.AddField(
            model_name="compdocimportaudit",
            name="unchanged_count",
            field=models.PositiveIntegerField(default=0),
        )
    ]
