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

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'last_seen'], name='device_active_seen_idx'),
        ]

    def __str__(self):
        return self.mac_address

    @property
    def latest_heartbeat(self):
        return self.heartbeats.first()

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


class HeartbeatLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='heartbeats')

    # ============================================================
    # ANA METRİKLER — Özet kartlar + grafikler
    # ============================================================
    cpu_percent = models.FloatField(default=0)          # Toplam CPU kullanımı (%)
    ram_percent = models.FloatField(default=0)          # RAM kullanımı (%)
    disk_percent = models.FloatField(default=0)         # Disk kullanımı (%)
    process_count = models.IntegerField(default=0)      # Çalışan süreç sayısı
    battery_percent = models.FloatField(null=True, blank=True)   # Batarya %
    battery_plugged = models.BooleanField(null=True, blank=True) # Şarjda mı?

    # ============================================================
    # CPU DETAY — Etkinlik Monitörü CPU sekmesi
    # ============================================================
    cpu_system = models.FloatField(default=0)           # Sistem CPU (%)
    cpu_user = models.FloatField(default=0)             # Kullanıcı CPU (%)
    cpu_idle = models.FloatField(default=0)             # Boş CPU (%)
    cpu_freq = models.FloatField(default=0)             # CPU frekansı (MHz)
    thread_count = models.IntegerField(default=0)       # İş parçacığı sayısı
    cpu_per_core   = models.JSONField(default=list, blank=True)      # Her çekirdek kullanımı [%]
    cpu_temperature = models.FloatField(null=True, blank=True)       # CPU sıcaklığı (°C), platform desteklemiyorsa None

    # ============================================================
    # BELLEK DETAY — Etkinlik Monitörü Bellek sekmesi
    # ============================================================
    memory_total = models.BigIntegerField(default=0)    # Fiziksel bellek (byte)
    memory_used = models.BigIntegerField(default=0)     # Kullanılan bellek (byte)
    memory_available = models.BigIntegerField(default=0)  # Kullanılabilir bellek (byte)
    memory_cached = models.BigIntegerField(default=0)   # Önbellekteki dosya (byte)
    swap_total = models.BigIntegerField(default=0)      # Toplam takas alanı (byte)
    swap_used = models.BigIntegerField(default=0)       # Kullanılan takas (byte)

    # ============================================================
    # DİSK DETAY — Etkinlik Monitörü Disk sekmesi
    # ============================================================
    disk_read_bytes = models.BigIntegerField(default=0)   # Toplam okunan (byte)
    disk_write_bytes = models.BigIntegerField(default=0)  # Toplam yazılan (byte)
    disk_partitions = models.JSONField(default=list, blank=True)  # Bölüm listesi

    # ============================================================
    # AĞ DETAY — Etkinlik Monitörü Ağ sekmesi
    # ============================================================
    net_bytes_sent   = models.BigIntegerField(default=0)     # Gönderilen veri (byte)
    net_bytes_recv   = models.BigIntegerField(default=0)     # Alınan veri (byte)
    net_packets_sent = models.BigIntegerField(default=0)     # Gönderilen paket
    net_packets_recv = models.BigIntegerField(default=0)     # Alınan paket
    net_per_nic      = models.JSONField(default=dict, blank=True)  # Arayüz bazında istatistikler

    # ============================================================
    # TOP İŞLEMLER — En çok CPU/RAM kullanan 10 uygulama
    # ============================================================
    # JSON formatında: [{"name":"Safari","cpu":12.5,"mem":387.2}, ...]
    top_processes = models.JSONField(default=list, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            # En kritik index: cihaza göre son kayıtları çekme (dashboard grafikleri)
            models.Index(fields=['device', '-timestamp'], name='heartbeat_device_ts_idx'),
        ]

    def __str__(self):
        return f"{self.device_id} - CPU:{self.cpu_percent}% RAM:{self.ram_percent}% - {self.timestamp}"


class HourlyAggregate(models.Model):
    """Bir cihazın belirli bir saate ait ortalama metriklerini saklar."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='hourly_stats')
    hour = models.DateTimeField()  # Saatin başlangıcı (dakika/saniye=0)

    cpu_avg = models.FloatField(default=0)
    cpu_max = models.FloatField(default=0)
    ram_avg = models.FloatField(default=0)
    ram_max = models.FloatField(default=0)
    disk_avg = models.FloatField(default=0)
    sample_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('device', 'hour')
        ordering = ['-hour']
        indexes = [
            models.Index(fields=['device', '-hour'], name='hourly_device_hour_idx'),
        ]

    def __str__(self):
        return f"{self.device_id} @ {self.hour:%Y-%m-%d %H:00} — CPU avg:{self.cpu_avg:.1f}%"


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
