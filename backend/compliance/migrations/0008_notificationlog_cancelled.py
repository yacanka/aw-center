from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0007_remove_coverpage_compliance_unique_project_cover_page_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationlog",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("claimed", "Claimed"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
