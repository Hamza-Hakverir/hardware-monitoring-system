# Veri taşıma migration'ı (kalıcı/geri alınamaz adım öncesi hazırlık):
#   1) Mevcut HeartbeatLog geçmişini (cihaz+gün bazında) dosya sistemi arşivine döker.
#   2) Device.live_metrics'i mevcut son heartbeat'lerden ve HourlyAggregate
#      satırlarından (son 24 saat) seed eder, böylece geçiş sırasında canlı
#      özet/grafikler boş kalmaz.
# Bir sonraki migration (0020) HeartbeatLog/HourlyAggregate tablolarını siler —
# bu adım onun ÖNÜNDE çalışmalı ki eski veri kaybolmadan arşive geçsin.
import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.db import migrations

HB_FIELDS = [
    'cpu_percent', 'ram_percent', 'disk_percent', 'process_count',
    'battery_percent', 'battery_plugged', 'cpu_system', 'cpu_user', 'cpu_idle',
    'cpu_freq', 'thread_count', 'cpu_per_core', 'cpu_temperature',
    'memory_total', 'memory_used', 'memory_available', 'memory_cached',
    'swap_total', 'swap_used', 'disk_read_bytes', 'disk_write_bytes',
    'disk_partitions', 'net_bytes_sent', 'net_bytes_recv', 'net_packets_sent',
    'net_packets_recv', 'net_per_nic', 'top_processes',
]


def _archive_device_dir(mac_address):
    archive_dir = Path(getattr(settings, 'ARCHIVE_DIR', Path(settings.BASE_DIR) / 'archive'))
    return archive_dir / mac_address.replace(':', '-')


def archive_and_seed_live_metrics(apps, schema_editor):
    Device = apps.get_model('monitoring', 'Device')
    HeartbeatLog = apps.get_model('monitoring', 'HeartbeatLog')
    HourlyAggregate = apps.get_model('monitoring', 'HourlyAggregate')

    for device in Device.objects.all().iterator():
        rows = list(HeartbeatLog.objects.filter(device=device).order_by('timestamp'))

        if rows:
            # --- ham geçmişi gün bazında grupla ve dosyaya yaz ---
            by_day = defaultdict(list)
            for hb in rows:
                by_day[hb.timestamp.date()].append(hb)

            device_dir = _archive_device_dir(device.mac_address)
            device_dir.mkdir(parents=True, exist_ok=True)
            for day, day_rows in by_day.items():
                file_path = device_dir / f"{day:%Y-%m-%d}.jsonl"
                with open(file_path, 'a', encoding='utf-8') as f:
                    for hb in day_rows:
                        record = {field: getattr(hb, field) for field in HB_FIELDS}
                        record['timestamp'] = hb.timestamp.isoformat()
                        f.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')

            # --- live_metrics['recent']: son 10 satır ---
            recent = []
            for hb in rows[-10:]:
                entry = {field: getattr(hb, field) for field in HB_FIELDS}
                entry['timestamp'] = hb.timestamp.isoformat()
                recent.append(entry)
        else:
            recent = []

        # --- live_metrics['windows']: mevcut HourlyAggregate satırlarından (son 24 saat) ---
        hourly_rows = list(HourlyAggregate.objects.filter(device=device).order_by('hour')[:24])
        windows = {}
        for metric, avg_field, max_field in [
            ('cpu_percent', 'cpu_avg', 'cpu_max'),
            ('ram_percent', 'ram_avg', 'ram_max'),
            ('disk_percent', 'disk_avg', None),  # HourlyAggregate'de disk_max yok — avg'ı yaklaşık max say
        ]:
            buckets = []
            total_sum = 0.0
            total_count = 0
            for hr in hourly_rows:
                count = hr.sample_count or 0
                avg = getattr(hr, avg_field) or 0.0
                bucket_sum = avg * count
                bucket_max = getattr(hr, max_field) if max_field else avg
                buckets.append({
                    'hour': hr.hour.replace(minute=0, second=0, microsecond=0).isoformat(),
                    'sum': bucket_sum,
                    'count': count,
                    'max': bucket_max,
                })
                total_sum += bucket_sum
                total_count += count
            windows[metric] = {'sum': total_sum, 'count': total_count, 'buckets': buckets}

        if recent or any(w['count'] for w in windows.values()):
            device.live_metrics = {'recent': recent, 'windows': windows}
            device.save(update_fields=['live_metrics'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0018_device_live_metrics'),
    ]

    operations = [
        migrations.RunPython(archive_and_seed_live_metrics, noop_reverse),
    ]
