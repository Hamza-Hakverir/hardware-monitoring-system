from rest_framework import serializers
from .models import Device, Location, HardwareSpec, HeartbeatLog, Alert


# ============================================================
# TEMEL SERİALİZER'LAR — Her model için basit CRUD işlemlerinde kullanılır
# ============================================================

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = '__all__'


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'


class HardwareSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = HardwareSpec
        fields = '__all__'


class HeartbeatLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeartbeatLog
        fields = '__all__'


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
        """Son heartbeat verisini döndürür (anlık CPU/RAM/Disk/Batarya)."""
        latest = obj.heartbeats.first()  # ordering = ['-timestamp'] olduğu için ilk = en yeni
        if latest:
            return HeartbeatLogSerializer(latest).data
        return None

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
