from django.db import migrations, models


def set_existing_no_limit(apps, schema_editor):
    Program = apps.get_model('core', 'Program')
    Program.objects.filter(capacity_current__lte=0).update(no_capacity_limit=True)


def unset_existing_no_limit(apps, schema_editor):
    Program = apps.get_model('core', 'Program')
    Program.objects.filter(no_capacity_limit=True, capacity_current=0).update(no_capacity_limit=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0071_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='program',
            name='no_capacity_limit',
            field=models.BooleanField(default=False, help_text='Program does not enforce a fixed capacity limit'),
        ),
        migrations.RunPython(set_existing_no_limit, unset_existing_no_limit),
    ]

