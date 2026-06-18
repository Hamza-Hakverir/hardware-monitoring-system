# Canlı özet (JSONB) alanı — yüksek frekanslı heartbeat verisini satır satır
# DB'ye yazmak yerine cihaz başına tek hücrede tutar (bkz. monitoring/live_stats.py).

import monitoring.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0017_device_heartbeat_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='live_metrics',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='device',
            name='token',
            field=models.CharField(default=monitoring.models._generate_device_token, max_length=64, unique=True),
        ),
    ]
