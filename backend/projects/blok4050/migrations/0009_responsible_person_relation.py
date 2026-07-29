import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blok4050", "0008_responsible_directory_person")]

    operations = [
        migrations.RemoveField(model_name="responsible", name="name"),
        migrations.RemoveField(model_name="responsible", name="email"),
        migrations.RemoveField(model_name="responsible", name="person_id"),
        migrations.RenameField(
            model_name="responsible", old_name="directory_person", new_name="person"
        ),
        migrations.AlterField(
            model_name="responsible",
            name="person",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_responsible_assignments",
                to="orgs.people",
            ),
        ),
        migrations.AlterModelOptions(
            name="responsible",
            options={"ordering": ["person__name", "person__person_id"]},
        ),
    ]
