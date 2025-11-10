import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0069_remove_servicerestriction_valid_scope_program_combination_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceRestrictionNotificationSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('email', models.EmailField(blank=True, help_text='Destination email for service restriction alerts (defaults to staff email if empty)', max_length=254, null=True)),
                ('notify_new', models.BooleanField(default=True, help_text='Receive notifications when new service restrictions are created')),
                ('notify_expiring', models.BooleanField(default=True, help_text='Receive notifications when service restrictions are nearing expiration')),
                ('staff', models.OneToOneField(help_text='Staff member who owns this subscription', on_delete=django.db.models.deletion.CASCADE, related_name='service_restriction_notification', to='core.staff')),
            ],
            options={
                'db_table': 'service_restriction_notification_subscriptions',
                'verbose_name': 'Service Restriction Notification Subscription',
                'verbose_name_plural': 'Service Restriction Notification Subscriptions',
            },
        ),
    ]

