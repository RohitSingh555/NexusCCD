# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0078_add_detection_source_to_client_duplicate'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='emhware_id',
            field=models.CharField(blank=True, db_index=True, help_text="Client ID from EMHware system", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='smis_id',
            field=models.CharField(blank=True, db_index=True, help_text="Client ID from SMIS system", max_length=100, null=True),
        ),
    ]

