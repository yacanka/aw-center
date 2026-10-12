"""Retire historical model state without dropping the adopted tables."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("dcc", "0002_dccreminderdelivery"), ("integrations", "0001_initial")]
    operations = [migrations.SeparateDatabaseAndState(database_operations=[], state_operations=[
        migrations.DeleteModel("JiraIssueDraftEvent"),
        migrations.DeleteModel("DccReminderDelivery"),
        migrations.DeleteModel("JiraIssueDraft"),
        migrations.DeleteModel("DccRecord"),
    ])]
