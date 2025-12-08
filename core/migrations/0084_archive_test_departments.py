# Generated manually

from django.db import migrations
from django.utils import timezone


def archive_test_departments(apps, schema_editor):
    """Archive test departments: Employment, Healthcare, Social Services, Test Dept"""
    Department = apps.get_model('core', 'Department')
    
    test_department_names = ['Employment', 'Healthcare', 'Social Services', 'Test Dept']
    now = timezone.now()
    
    for dept_name in test_department_names:
        try:
            department = Department.objects.get(name=dept_name)
            department.is_archived = True
            department.archived_at = now
            department.save(update_fields=['is_archived', 'archived_at'])
        except Department.DoesNotExist:
            # Department doesn't exist, skip it
            pass


def reverse_archive_test_departments(apps, schema_editor):
    """Reverse: Unarchive test departments"""
    Department = apps.get_model('core', 'Department')
    
    test_department_names = ['Employment', 'Healthcare', 'Social Services', 'Test Dept']
    
    for dept_name in test_department_names:
        try:
            department = Department.objects.get(name=dept_name)
            department.is_archived = False
            department.archived_at = None
            department.save()
        except Department.DoesNotExist:
            # Department doesn't exist, skip it
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0083_optimize_client_indexes'),
    ]

    operations = [
        migrations.RunPython(archive_test_departments, reverse_archive_test_departments),
    ]
