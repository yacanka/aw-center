from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compliance", "0002_initial")]

    operations = [
        migrations.AlterField(
            model_name="reviewtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("changes_requested", "Changes requested"),
                    ("cancelled", "Cancelled"),
                    ("superseded", "Superseded"),
                ],
                default="pending",
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="reviewtask",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("document", "kind", "assignee", "source_version"),
                name="compliance_unique_pending_review_source",
            ),
        ),
    ]
