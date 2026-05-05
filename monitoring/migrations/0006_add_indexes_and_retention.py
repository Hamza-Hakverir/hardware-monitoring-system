from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0005_heartbeatlog_cpu_freq_heartbeatlog_cpu_idle_and_more"),
    ]

    operations = [
        # HeartbeatLog: cihaz + zaman bazlı sorgular için (en kritik)
        migrations.AddIndex(
            model_name="heartbeatlog",
            index=models.Index(
                fields=["device", "-timestamp"],
                name="heartbeat_device_ts_idx",
            ),
        ),
        # Alert: çözülmemiş uyarıları zaman sıralı çekme
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["is_resolved", "-created_at"],
                name="alert_resolved_ts_idx",
            ),
        ),
        # Alert: cihaza ait uyarıları zaman sıralı çekme
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["device", "-created_at"],
                name="alert_device_ts_idx",
            ),
        ),
        # Device: pasif cihaz tespiti için (mark_stale_devices_inactive)
        migrations.AddIndex(
            model_name="device",
            index=models.Index(
                fields=["is_active", "last_seen"],
                name="device_active_seen_idx",
            ),
        ),
    ]
