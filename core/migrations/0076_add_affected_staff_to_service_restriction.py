# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0075_add_preferred_communication_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerestriction',
            name='affected_staff',
            field=models.ForeignKey(blank=True, db_index=True, help_text='Staff member who is affected by or involved in this restriction', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='restrictions_affecting', to='core.staff'),
        ),
    ]

