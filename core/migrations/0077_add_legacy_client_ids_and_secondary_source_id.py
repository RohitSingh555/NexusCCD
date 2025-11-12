# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0076_add_affected_staff_to_service_restriction'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='legacy_client_ids',
            field=models.JSONField(default=list, help_text="List of legacy client IDs from different sources (e.g., [{'source': 'SMIS', 'client_id': '123'}, {'source': 'EMHware', 'client_id': '456'}])"),
        ),
        migrations.AddField(
            model_name='client',
            name='secondary_source_id',
            field=models.CharField(blank=True, db_index=True, help_text="Client ID of the duplicate client that was merged into this client", max_length=100, null=True),
        ),
    ]

