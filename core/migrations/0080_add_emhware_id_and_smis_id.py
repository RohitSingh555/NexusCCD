# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0079_rename_notifications_staff_i_c13930_idx_notificatio_staff_i_fd6636_idx_and_more'),
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

