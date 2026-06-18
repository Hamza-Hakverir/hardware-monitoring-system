from rest_framework import serializers
from .models import Device, Location, HardwareSpec, Alert


# ============================================================
# TEMEL SERİALİZER'LAR — Her model için basit CRUD işlemlerinde kullanılır
# ============================================================

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ['mac_address', 'os_info', 'is_active', 'last_seen', 'created_at', 'went_online_at']


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'


class HardwareSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = HardwareSpec
        fields = '__all__'


class HeartbeatPayloadSerializer(serializers.Serializer):
    """agent.py'den gelen heartbeat gövdesini doğrular.
    Artık bir model'e karşılık gelmiyor — heartbeat'ler DB satırı olarak
    saklanmıyor (bkz. Device.live_metrics + monitoring/archive.py).
    """
    device = serializers.CharField(max_length=17)

    # Ana metrikler
    cpu_percent = serializers.FloatField()
    ram_percent = serializers.FloatField()
    disk_percent = serializers.FloatField()
    process_count = serializers.IntegerField()
    battery_percent = serializers.FloatField(allow_null=True, required=False)
    battery_plugged = serializers.BooleanField(allow_null=True, required=False)

    # CPU detay
    cpu_system = serializers.FloatField(required=False, default=0)
    cpu_user = serializers.FloatField(required=False, default=0)
    cpu_idle = serializers.FloatField(required=False, default=0)
    cpu_freq = serializers.FloatField(required=False, default=0)
    thread_count = serializers.IntegerField(required=False, default=0)
    cpu_per_core = serializers.ListField(required=False, default=list)
    cpu_temperature = serializers.FloatField(allow_null=True, required=False)

    # Bellek detay
    memory_total = serializers.IntegerField(required=False, default=0)
    memory_used = serializers.IntegerField(required=False, default=0)
    memory_available = serializers.IntegerField(required=False, default=0)
    memory_cached = serializers.IntegerField(required=False, default=0)
    swap_total = serializers.IntegerField(required=False, default=0)
    swap_used = serializers.IntegerField(required=False, default=0)

    # Disk detay
    disk_read_bytes = serializers.IntegerField(required=False, default=0)
    disk_write_bytes = serializers.IntegerField(required=False, default=0)
    disk_partitions = serializers.ListField(required=False, default=list)

    # Ağ detay
    net_bytes_sent = serializers.IntegerField(required=False, default=0)
    net_bytes_recv = serializers.IntegerField(required=False, default=0)
    net_packets_sent = serializers.IntegerField(required=False, default=0)
    net_packets_recv = serializers.IntegerField(required=False, default=0)
    net_per_nic = serializers.DictField(required=False, default=dict)

    # Top işlemler
    top_processes = serializers.ListField(required=False, default=list)


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = '__all__'


# ============================================================
# NESTED SERİALİZER'LAR — Cihaz detay sayfası için
# ============================================================
# Bir cihazın TÜM bilgilerini tek istekte döndürür:
# Cihaz + Konum + Donanım + Son Heartbeat + Uyarılar

class DeviceDetailSerializer(serializers.ModelSerializer):
    """Cihaz detay sayfasında kullanılır.
    Tek bir API isteğiyle cihazın tüm bilgilerini döndürür.
    """
    location = LocationSerializer(read_only=True)
    hardware = HardwareSpecSerializer(read_only=True)
    latest_heartbeat = serializers.SerializerMethodField()
    recent_alerts = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            'mac_address', 'os_info', 'is_active', 'last_seen', 'created_at',
            'location', 'hardware', 'latest_heartbeat', 'recent_alerts',
        ]

    def get_latest_heartbeat(self, obj):
        """Son heartbeat verisini döndürür (anlık CPU/RAM/Disk/Batarya) — Device.live_metrics'ten."""
        recent = obj.live_metrics.get('recent') or []
        return recent[-1] if recent else None

    def get_recent_alerts(self, obj):
        """Son 5 uyarıyı döndürür."""
        alerts = obj.alerts.order_by('-created_at')[:5]
        return AlertSerializer(alerts, many=True).data


# ============================================================
# DASHBOARD SERİALİZER — Özet istatistikler için
# ============================================================

class DashboardStatsSerializer(serializers.Serializer):
    """Dashboard sayfasındaki özet kartları için veri yapısı.
    Bu bir ModelSerializer değil — elle tanımlanmış alanlar.
    """
    total_devices = serializers.IntegerField()
    active_devices = serializers.IntegerField()
    inactive_devices = serializers.IntegerField()
    total_alerts = serializers.IntegerField()
    unresolved_alerts = serializers.IntegerField()
    recent_alerts = AlertSerializer(many=True)
