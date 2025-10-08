# Generated manually to add created_by field to ClientProgramEnrollment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_alter_client_client_id_alter_client_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientprogramenrollment',
            name='created_by',
            field=models.CharField(blank=True, help_text='Name of the person who created this record', max_length=255, null=True),
        ),
    ]
