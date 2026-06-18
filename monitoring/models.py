import secrets

from django.db import models
from django.utils import timezone


def _generate_device_token():
    return secrets.token_hex(32)


class Device(models.Model):
    mac_address    = models.CharField(max_length=17, primary_key=True, unique=True)
    os_info        = models.CharField(max_length=255)
    is_active      = models.BooleanField(default=True)
    last_seen      = models.DateTimeField(auto_now=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    went_online_at = models.DateTimeField(null=True, blank=True)
    token           = models.CharField(max_length=64, unique=True, default=_generate_device_token)
    tags            = models.ManyToManyField('Tag', blank=True, related_name='devices')
    heartbeat_count = models.PositiveIntegerField(default=0)

    # Canlı özet — yüksek frekanslı heartbeat verisini satır satır DB'ye yazmak
    # yerine cihaz başına tek JSONB hücrede tutar. Yapı (bkz. monitoring/live_stats.py):
    #   {
    #     "recent":  [ {...tam heartbeat payload..., "timestamp": "..."} ],  # en fazla 10
    #     "windows": {
    #         "cpu_percent":  {"sum": ..., "count": ..., "buckets": [{"hour", "sum", "count", "max"}, ...]},
    #         "ram_percent":  {...},
    #         "disk_percent": {...},
    #     },
    #   }
    # "windows" saatlik bucket'larla gerçek kayan 24 saatlik ortalamayı O(1) günceller
    # (bkz. live_stats.apply_heartbeat).
    live_metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'last_seen'], name='device_active_seen_idx'),
        ]

    def __str__(self):
        return self.mac_address

    @property
    def latest_heartbeat(self):
        recent = self.live_metrics.get('recent') or []
        return recent[-1] if recent else None

    @property
    def uptime_display(self):
        """Online süresini '3 sa 24 dk' formatında döndürür."""
        if not self.is_active or not self.went_online_at:
            return None
        delta = timezone.now() - self.went_online_at
        total_seconds = int(delta.total_seconds())
        days    = total_seconds // 86400
        hours   = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        if days:
            return f'{days} gün {hours} sa'
        if hours:
            return f'{hours} sa {minutes} dk'
        return f'{minutes} dk'


class Location(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='location')
    building = models.CharField(max_length=100)
    floor = models.CharField(max_length=50)
    room = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.building} - {self.floor} - {self.room} ({self.device_id})"


class HardwareSpec(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='hardware')
    cpu_info = models.CharField(max_length=255)                              # İşlemci modeli
    ram_total = models.CharField(max_length=50)                              # Toplam RAM
    vga_info = models.CharField(max_length=255)                              # Ekran kartı
    hostname = models.CharField(max_length=255, blank=True, default='')      # Bilgisayar adı
    ip_address = models.CharField(max_length=45, blank=True, default='')     # Ağ IP adresi
    cpu_cores = models.IntegerField(default=0)                               # Fiziksel çekirdek
    cpu_threads = models.IntegerField(default=0)                             # Mantıksal thread
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname or self.device_id} — {self.cpu_info}"


class Tag(models.Model):
    """Cihazlara atanabilen etiket (Sunucu, Masaüstü, Laptop…)"""
    name  = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6c757d')

    def __str__(self):
        return self.name


class DeviceThreshold(models.Model):
    """Cihaza özel alert eşikleri. Yoksa global settings değerleri kullanılır."""
    device        = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='threshold')
    cpu_warning   = models.FloatField(default=75.0)
    cpu_critical  = models.FloatField(default=90.0)
    ram_warning   = models.FloatField(default=75.0)
    ram_critical  = models.FloatField(default=90.0)
    disk_warning  = models.FloatField(default=75.0)
    disk_critical = models.FloatField(default=90.0)

    def __str__(self):
        return f"{self.device_id} eşikleri"


class DeviceStatusLog(models.Model):
    """Cihazın online/offline geçiş kayıtları (zaman çizelgesi için)."""
    device      = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='status_logs')
    went_online = models.BooleanField()  # True=online oldu, False=offline oldu
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', '-timestamp'], name='statuslog_device_ts_idx'),
        ]

    def __str__(self):
        return f"{self.device_id} → {'online' if self.went_online else 'offline'} @ {self.timestamp}"


class Alert(models.Model):
    SEVERITY_WARNING  = 'WARNING'
    SEVERITY_CRITICAL = 'CRITICAL'
    SEVERITY_CHOICES  = [(SEVERITY_WARNING, 'Uyarı'), (SEVERITY_CRITICAL, 'Kritik')]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=50)
    severity   = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_CRITICAL)
    message = models.TextField()
    is_resolved     = models.BooleanField(default=False)
    notified        = models.BooleanField(default=False)
    resolution_note = models.TextField(blank=True, default='')
    resolved_at     = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_resolved', '-created_at'], name='alert_resolved_ts_idx'),
            models.Index(fields=['device', '-created_at'], name='alert_device_ts_idx'),
        ]

    def __str__(self):
        return f"{self.alert_type} for {self.device_id} - Resolved: {self.is_resolved}"
