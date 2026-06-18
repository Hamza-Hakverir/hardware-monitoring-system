# ⚠️ Geri alınamaz: HeartbeatLog ve HourlyAggregate tablolarını kaldırır.
# Yalnızca 0019'daki veri taşıma (arşive dökme + live_metrics seed) tamamlandıktan
# sonra çalıştırılmalıdır.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0019_archive_legacy_heartbeats'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='hourlyaggregate',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='hourlyaggregate',
            name='device',
        ),
        migrations.DeleteModel(
            name='HeartbeatLog',
        ),
        migrations.DeleteModel(
            name='HourlyAggregate',
        ),
    ]
