import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0013_device_token_alert_notified'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceThreshold',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cpu_warning',   models.FloatField(default=75.0)),
                ('cpu_critical',  models.FloatField(default=90.0)),
                ('ram_warning',   models.FloatField(default=75.0)),
                ('ram_critical',  models.FloatField(default=90.0)),
                ('disk_warning',  models.FloatField(default=75.0)),
                ('disk_critical', models.FloatField(default=90.0)),
                ('device', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='threshold',
                    to='monitoring.device',
                )),
            ],
        ),
        migrations.CreateModel(
            name='DeviceStatusLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('went_online', models.BooleanField()),
                ('timestamp',   models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='status_logs',
                    to='monitoring.device',
                )),
            ],
            options={
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['device', '-timestamp'], name='statuslog_device_ts_idx'),
                ],
            },
        ),
    ]
