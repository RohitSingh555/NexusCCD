# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0078_add_legacy_client_ids_and_secondary_source_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientduplicate',
            name='detection_source',
            field=models.CharField(blank=True, db_index=True, help_text="How this duplicate was detected (e.g., 'scan', 'upload', 'manual')", max_length=50, null=True),
        ),
    ]

