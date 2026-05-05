from django.db import models


class Device(models.Model):
    mac_address = models.CharField(max_length=17, primary_key=True, unique=True)
    os_info = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'last_seen'], name='device_active_seen_idx'),
        ]

    def __str__(self):
        return self.mac_address

    @property
    def latest_heartbeat(self):
        return self.heartbeats.first()


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

    # ============================================================
    # AĞ DETAY — Etkinlik Monitörü Ağ sekmesi
    # ============================================================
    net_bytes_sent = models.BigIntegerField(default=0)    # Gönderilen veri (byte)
    net_bytes_recv = models.BigIntegerField(default=0)    # Alınan veri (byte)
    net_packets_sent = models.BigIntegerField(default=0)  # Gönderilen paket
    net_packets_recv = models.BigIntegerField(default=0)  # Alınan paket

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


class Alert(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=50)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_resolved', '-created_at'], name='alert_resolved_ts_idx'),
            models.Index(fields=['device', '-created_at'], name='alert_device_ts_idx'),
        ]

    def __str__(self):
        return f"{self.alert_type} for {self.device_id} - Resolved: {self.is_resolved}"
