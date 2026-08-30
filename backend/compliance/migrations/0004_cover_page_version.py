from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compliance", "0003_review_integrity")]

    operations = [
        migrations.AddField(
            model_name="coverpage",
            name="version",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="historicalcoverpage",
            name="version",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
