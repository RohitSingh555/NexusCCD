# Generated manually to add is_archived field and archived status to ClientProgramEnrollment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_add_created_by_to_enrollment'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientprogramenrollment',
            name='is_archived',
            field=models.BooleanField(db_index=True, default=False, help_text='Whether this enrollment is archived'),
        ),
        migrations.AlterField(
            model_name='clientprogramenrollment',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('suspended', 'Suspended'), ('archived', 'Archived')], db_index=True, default='pending', max_length=20),
        ),
    ]

