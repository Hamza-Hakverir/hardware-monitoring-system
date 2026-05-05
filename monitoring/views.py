from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Device, Location, HardwareSpec, HeartbeatLog, Alert
from .serializers import (
    DeviceSerializer, LocationSerializer, HardwareSpecSerializer,
    HeartbeatLogSerializer, AlertSerializer,
    DeviceDetailSerializer, DashboardStatsSerializer
)


# ============================================================
# YARDIMCI FONKSİYON — Eski cihazları otomatik pasifleştir
# ============================================================
STALE_THRESHOLD_MINUTES = 2  # 2 dakika sinyal gelmezse → pasif
HEARTBEAT_LIMIT = 1440       # Cihaz başına max kayıt (15sn × 1440 = 6 saat)
CLEANUP_EVERY = 96           # Her 96 yeni kayıtta bir temizlik yap (≈24 dakika)

def mark_stale_devices_inactive():
    """Son 2 dakikada heartbeat göndermeyen cihazları pasif yapar.
    Her sayfa yüklendiğinde çağrılır — böylece gerçek durumu yansıtır.
    """
    cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    Device.objects.filter(is_active=True, last_seen__lt=cutoff).update(is_active=False)


# ============================================================
# API VIEWS — REST API Endpoint'leri
# ============================================================

# 1. Yeni cihaz kaydı (POST)
@api_view(['POST'])
def register_device(request):
    serializer = DeviceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 2. Sinyal (Heartbeat) alma (POST)
# Agent her 15 saniyede bir bu endpoint'e veri gönderir.
# Gelen veri: device (MAC), cpu_percent, ram_percent, disk_percent,
#             process_count, battery_percent, battery_plugged
@api_view(['POST'])
def receive_heartbeat(request):
    serializer = HeartbeatLogSerializer(data=request.data)
    if serializer.is_valid():
        heartbeat = serializer.save()

        # Cihazı aktif olarak işaretle ve last_seen güncelle
        device = heartbeat.device
        device.is_active = True
        device.save(update_fields=['is_active', 'last_seen'])

        # Eşik kontrolü: CPU, RAM veya Disk %90'ı geçerse otomatik alert oluştur
        threshold = 90.0
        if heartbeat.cpu_percent >= threshold:
            Alert.objects.create(
                device=device,
                alert_type='CPU_HIGH',
                message=f'CPU kullanımı kritik seviyede: %{heartbeat.cpu_percent:.1f}'
            )
        if heartbeat.ram_percent >= threshold:
            Alert.objects.create(
                device=device,
                alert_type='RAM_HIGH',
                message=f'RAM kullanımı kritik seviyede: %{heartbeat.ram_percent:.1f}'
            )
        if heartbeat.disk_percent >= threshold:
            Alert.objects.create(
                device=device,
                alert_type='DISK_FULL',
                message=f'Disk kullanımı kritik seviyede: %{heartbeat.disk_percent:.1f}'
            )

        # Otomatik temizleme: her CLEANUP_EVERY kayıtta bir eski heartbeat'leri sil
        total = device.heartbeats.count()
        if total > HEARTBEAT_LIMIT + CLEANUP_EVERY:
            # N. kaydın timestamp'ini bul, ondan eskilerini sil (ID listesi yüklemekten çok daha verimli)
            cutoff_ts = device.heartbeats.values_list('timestamp', flat=True)[HEARTBEAT_LIMIT:HEARTBEAT_LIMIT + 1]
            if cutoff_ts:
                device.heartbeats.filter(timestamp__lte=cutoff_ts[0]).delete()

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 3. Tüm cihazları listeleme (GET)
@api_view(['GET'])
def list_devices(request):
    devices = Device.objects.all()
    serializer = DeviceSerializer(devices, many=True)
    return Response(serializer.data)

# 4. Tek bir cihazın detayını getirme — NESTED (GET)
# Cihaz + Konum + Donanım + Son Heartbeat + Son 5 Alert birlikte döner
@api_view(['GET'])
def device_detail(request, pk):
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Cihaz bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    serializer = DeviceDetailSerializer(device)
    return Response(serializer.data)

# 5. Konum (Location) ekleme (POST)
@api_view(['POST'])
def add_location(request):
    serializer = LocationSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 6. Tüm konumları listeleme (GET)
@api_view(['GET'])
def list_locations(request):
    locations = Location.objects.all()
    serializer = LocationSerializer(locations, many=True)
    return Response(serializer.data)

# 7. Donanım (HardwareSpec) güncelleme (POST)
@api_view(['POST'])
def update_hardware(request):
    device_id = request.data.get('device')
    existing = HardwareSpec.objects.filter(device_id=device_id).first()
    if existing:
        serializer = HardwareSpecSerializer(existing, data=request.data, partial=True)
        response_status = status.HTTP_200_OK
    else:
        serializer = HardwareSpecSerializer(data=request.data)
        response_status = status.HTTP_201_CREATED

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=response_status)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 8. Tek cihazın donanım bilgisini getirme (GET)
@api_view(['GET'])
def get_hardware(request, device_id):
    try:
        hardware = HardwareSpec.objects.get(device_id=device_id)
    except HardwareSpec.DoesNotExist:
        return Response({'error': 'Donanım bilgisi bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    serializer = HardwareSpecSerializer(hardware)
    return Response(serializer.data)

# 9. Tüm uyarıları (Alerts) listeleme (GET)
@api_view(['GET'])
def list_alerts(request):
    alerts = Alert.objects.all()
    serializer = AlertSerializer(alerts, many=True)
    return Response(serializer.data)

# 10. Bir uyarıyı "çözüldü" olarak işaretleme (POST/PATCH)
@api_view(['POST', 'PATCH'])
def resolve_alert(request, pk):
    try:
        alert = Alert.objects.get(pk=pk)
    except Alert.DoesNotExist:
        return Response({'error': 'Uyarı bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    alert.is_resolved = True
    alert.save()
    serializer = AlertSerializer(alert)
    return Response(serializer.data)


# ============================================================
# YENİ API VIEWS — Dashboard & Grafik verileri
# ============================================================

# 11. Cihaz performans istatistikleri (GET) — Chart.js için
# Son 30 heartbeat kaydını döndürür → grafik çizmek için
@api_view(['GET'])
def device_stats(request, pk):
    """Bir cihazın son 30 heartbeat verisini döndürür.
    Chart.js line chart bu veriyi kullanarak CPU/RAM/Disk grafiği çizer.
    """
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Cihaz bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    # Önce en yeni 30'u al, sonra ters çevir → Chart.js soldan sağa doğru zaman ekseni
    heartbeats = list(reversed(list(device.heartbeats.all()[:30])))
    serializer = HeartbeatLogSerializer(heartbeats, many=True)
    return Response({
        'device': pk,
        'count': len(serializer.data),
        'heartbeats': serializer.data,
    })

# 12. Dashboard özet istatistikleri (GET)
# Dashboard sayfasındaki kartlar için toplam sayıları döndürür
@api_view(['GET'])
def dashboard_stats(request):
    """Dashboard kartları için özet verileri döndürür:
    - Toplam / Aktif / Pasif cihaz sayısı
    - Toplam / Çözülmemiş uyarı sayısı
    - Son 5 uyarı
    """
    total = Device.objects.count()
    active = Device.objects.filter(is_active=True).count()
    unresolved = Alert.objects.filter(is_resolved=False).count()
    recent = Alert.objects.order_by('-created_at')[:5]

    data = {
        'total_devices': total,
        'active_devices': active,
        'inactive_devices': total - active,
        'total_alerts': Alert.objects.count(),
        'unresolved_alerts': unresolved,
        'recent_alerts': AlertSerializer(recent, many=True).data,
    }
    return Response(data)


# ============================================================
# UI VIEWS — Django Template ile web sayfaları
# ============================================================

def dashboard_view(request):
    """Ana sayfa — Dashboard.
    Özet kartlar, grafik ve son uyarılar gösterilir.
    """
    mark_stale_devices_inactive()  # 2 dk sinyal gelmeyenleri pasif yap

    total = Device.objects.count()
    active = Device.objects.filter(is_active=True).count()
    unresolved = Alert.objects.filter(is_resolved=False).count()
    recent_alerts = Alert.objects.order_by('-created_at')[:5]

    context = {
        'total_devices': total,
        'active_devices': active,
        'inactive_devices': total - active,
        'unresolved_alerts': unresolved,
        'recent_alerts': recent_alerts,
    }
    return render(request, 'monitoring/dashboard.html', context)


def device_list_view(request):
    """Cihaz listesi sayfası — tüm cihazlar tablo halinde."""
    mark_stale_devices_inactive()  # 2 dk sinyal gelmeyenleri pasif yap
    devices = Device.objects.select_related('location', 'hardware').all()
    return render(request, 'monitoring/device_list.html', {'devices': devices})


def device_detail_view(request, pk):
    """Cihaz detay sayfası — tek cihazın tüm bilgileri + grafikler.
    select_related ile konum ve donanım bilgisi tek sorguyla getirilir.
    prefetch_related ile son heartbeat'ler ve alertler çekilir.
    """
    device = get_object_or_404(Device, pk=pk)
    hardware = getattr(device, 'hardware', None)
    location = getattr(device, 'location', None)
    recent_heartbeats = device.heartbeats.all()[:30]
    recent_alerts = device.alerts.order_by('-created_at')[:10]
    latest_hb = device.heartbeats.first()

    context = {
        'device': device,
        'hardware': hardware,
        'location': location,
        'recent_heartbeats': recent_heartbeats,
        'recent_alerts': recent_alerts,
        'latest_hb': latest_hb,
    }
    return render(request, 'monitoring/device_detail.html', context)


def alert_list_view(request):
    """Uyarı listesi sayfası."""
    alerts = Alert.objects.all().order_by('-created_at')
    return render(request, 'monitoring/alert_list.html', {'alerts': alerts})


def add_alert_view(request):
    """Manuel uyarı ekleme formu."""
    error = None
    if request.method == 'POST':
        device_mac = request.POST.get('device')
        alert_type = request.POST.get('alert_type')
        message = request.POST.get('message')
        try:
            device = Device.objects.get(mac_address=device_mac)
            Alert.objects.create(device=device, alert_type=alert_type, message=message)
            return redirect('ui_alert_list')
        except Device.DoesNotExist:
            error = 'Seçilen cihaz bulunamadı.'

    devices = Device.objects.all()
    return render(request, 'monitoring/add_alert.html', {'devices': devices, 'error': error})


def add_location_view(request):
    """Cihaza konum atama formu."""
    error = None
    if request.method == 'POST':
        device_mac = request.POST.get('device')
        building = request.POST.get('building')
        floor = request.POST.get('floor')
        room = request.POST.get('room')
        try:
            device = Device.objects.get(mac_address=device_mac)
            Location.objects.update_or_create(
                device=device,
                defaults={'building': building, 'floor': floor, 'room': room}
            )
            return redirect('ui_device_list')
        except Device.DoesNotExist:
            error = 'Seçilen cihaz bulunamadı.'

    devices = Device.objects.all()
    return render(request, 'monitoring/add_location.html', {'devices': devices, 'error': error})
