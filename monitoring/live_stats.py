"""
Cihaz başına tek satırlık özet (Device.live_metrics JSONB) üzerinde çalışan
saf fonksiyonlar — DB'ye dokunmaz, test edilebilir.

Matematik (24 saatlik kayan ortalama):
    Her metrik (cpu/ram/disk) için saatlik bucket'lar tutulur: {hour, sum, count, max}.
    Yeni değer v geldiğinde:
        bucket.sum   += v ;  bucket.count   += 1      (ilgili saate)
        window.sum   += v ;  window.count   += 1      (O(1) — toplamı yeniden hesaplamaz)
    24 saatten eski bucket'lar penceredeyken (yeni saate geçişte) düşürülür:
        window.sum   -= evicted.sum
        window.count -= evicted.count
    Ortalama her zaman window.sum / window.count.

    Takvim günü sıfırlaması YOKTUR — pencere gerçek anlamda kayar, böylece gece
    yarısında ortalama aniden sıfırlanıp zıplamaz.
"""
from datetime import timedelta

RECENT_LIMIT = 10
WINDOW_HOURS = 24
WINDOW_METRICS = ('cpu_percent', 'ram_percent', 'disk_percent')


def _floor_hour_iso(dt):
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()


def _empty_window():
    return {'sum': 0.0, 'count': 0, 'buckets': []}


def apply_heartbeat(live_metrics, payload, now):
    """live_metrics (dict) içine yeni bir heartbeat uygular ve güncellenmiş dict'i döner."""
    live_metrics = dict(live_metrics or {})

    recent = list(live_metrics.get('recent') or [])
    entry = dict(payload)
    entry['timestamp'] = now.isoformat()
    recent.append(entry)
    if len(recent) > RECENT_LIMIT:
        recent = recent[-RECENT_LIMIT:]
    live_metrics['recent'] = recent

    windows = dict(live_metrics.get('windows') or {})
    hour_key = _floor_hour_iso(now)
    cutoff_hour = _floor_hour_iso(now - timedelta(hours=WINDOW_HOURS))

    for metric in WINDOW_METRICS:
        window = dict(windows.get(metric) or _empty_window())
        value = float(payload.get(metric) or 0)
        buckets = list(window.get('buckets') or [])

        if not buckets or buckets[-1]['hour'] != hour_key:
            buckets.append({'hour': hour_key, 'sum': 0.0, 'count': 0, 'max': value})
        bucket = buckets[-1]
        bucket['sum'] += value
        bucket['count'] += 1
        bucket['max'] = max(bucket['max'], value)

        window['sum'] = window.get('sum', 0.0) + value
        window['count'] = window.get('count', 0) + 1

        while buckets and buckets[0]['hour'] < cutoff_hour:
            evicted = buckets.pop(0)
            window['sum'] -= evicted['sum']
            window['count'] -= evicted['count']

        window['buckets'] = buckets
        windows[metric] = window

    live_metrics['windows'] = windows
    live_metrics['last_seen'] = now.isoformat()
    return live_metrics


def window_average(live_metrics, metric):
    """Son WINDOW_HOURS saatlik kayan ortalama. Veri yoksa None."""
    window = (live_metrics.get('windows') or {}).get(metric) or {}
    count = window.get('count', 0)
    if not count:
        return None
    return window['sum'] / count


def hourly_trend(live_metrics, hours=WINDOW_HOURS):
    """device_hourly_trend endpoint'i için eski HourlyAggregate formatına eşdeğer liste üretir.
    cpu/ram/disk bucket'ları her heartbeat'te birlikte güncellendiği için aynı index'te aynı saate denk gelir.
    """
    windows = live_metrics.get('windows') or {}
    cpu_buckets = (windows.get('cpu_percent') or {}).get('buckets', [])[-hours:]
    ram_buckets = (windows.get('ram_percent') or {}).get('buckets', [])[-hours:]
    disk_buckets = (windows.get('disk_percent') or {}).get('buckets', [])[-hours:]

    rows = []
    for cpu_b, ram_b, disk_b in zip(cpu_buckets, ram_buckets, disk_buckets):
        rows.append({
            'hour': cpu_b['hour'],
            'cpu_avg': round(cpu_b['sum'] / cpu_b['count'], 1) if cpu_b['count'] else 0,
            'cpu_max': round(cpu_b['max'], 1),
            'ram_avg': round(ram_b['sum'] / ram_b['count'], 1) if ram_b['count'] else 0,
            'ram_max': round(ram_b['max'], 1),
            'disk_avg': round(disk_b['sum'] / disk_b['count'], 1) if disk_b['count'] else 0,
            'sample_count': cpu_b['count'],
        })
    return rows
