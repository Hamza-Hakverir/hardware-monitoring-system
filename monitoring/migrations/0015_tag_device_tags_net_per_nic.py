from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0014_devicethreshold_devicestatuslog'),
    ]

    operations = [
        # Tag modeli
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id',    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name',  models.CharField(max_length=50, unique=True)),
                ('color', models.CharField(default='#6c757d', max_length=7)),
            ],
        ),
        # Device.tags M2M
        migrations.AddField(
            model_name='device',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='devices', to='monitoring.tag'),
        ),
        # HeartbeatLog.net_per_nic JSON
        migrations.AddField(
            model_name='heartbeatlog',
            name='net_per_nic',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
