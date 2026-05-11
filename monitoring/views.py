from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Avg, Max, Subquery, OuterRef, FloatField
from django.conf import settings
from django.core.paginator import Paginator
import logging

logger = logging.getLogger('monitoring')
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Device, Location, HardwareSpec, HeartbeatLog, Alert, HourlyAggregate
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


def aggregate_completed_hours(device):
    """Son 25 saatin tamamlanmış saatlerini HourlyAggregate'e yazar (upsert).
    Temizlik sırasında çağrılır — tamamlanmamış mevcut saat dahil edilmez.
    """
    from django.db.models import Count
    from django.db.models.functions import TruncHour

    now = timezone.now()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    since = current_hour - timedelta(hours=25)

    rows = (
        device.heartbeats
        .filter(timestamp__gte=since, timestamp__lt=current_hour)
        .annotate(hour=TruncHour('timestamp'))
        .values('hour')
        .annotate(
            cpu_avg=Avg('cpu_percent'),
            cpu_max=Max('cpu_percent'),
            ram_avg=Avg('ram_percent'),
            ram_max=Max('ram_percent'),
            disk_avg=Avg('disk_percent'),
            cnt=Count('id'),
        )
    )
    for row in rows:
        HourlyAggregate.objects.update_or_create(
            device=device,
            hour=row['hour'],
            defaults={
                'cpu_avg': round(row['cpu_avg'] or 0, 1),
                'cpu_max': round(row['cpu_max'] or 0, 1),
                'ram_avg': round(row['ram_avg'] or 0, 1),
                'ram_max': round(row['ram_max'] or 0, 1),
                'disk_avg': round(row['disk_avg'] or 0, 1),
                'sample_count': row['cnt'],
            }
        )


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

        # Cihazı aktif olarak işaretle ve last_seen güncelle.
        # Pasif → aktif geçişinde went_online_at kaydet (uptime başlangıcı).
        device = heartbeat.device
        update_fields = ['is_active', 'last_seen']
        if not device.is_active:
            device.went_online_at = timezone.now()
            update_fields.append('went_online_at')
        device.is_active = True
        device.save(update_fields=update_fields)

        # Eşik kontrolü: WARNING (%75) ve CRITICAL (%90) iki seviyeli alert.
        # Aynı cihaz + aynı tür için zaten çözülmemiş alert varsa yeni yaratma.
        warn_thr = settings.ALERT_WARNING_THRESHOLD
        crit_thr = settings.ALERT_CRITICAL_THRESHOLD
        metric_checks = [
            (heartbeat.cpu_percent,  'CPU_HIGH',  'CPU'),
            (heartbeat.ram_percent,  'RAM_HIGH',  'RAM'),
            (heartbeat.disk_percent, 'DISK_FULL', 'Disk'),
        ]
        # Mevcut aktif alert'lerin (type, severity) çiftlerini al
        active_alerts = set(
            Alert.objects.filter(device=device, is_resolved=False)
                         .values_list('alert_type', 'severity')
        )
        for value, alert_type, label in metric_checks:
            if value >= crit_thr and (alert_type, Alert.SEVERITY_CRITICAL) not in active_alerts:
                msg = f'{label} kullanımı KRİTİK seviyede: %{value:.1f}'
                Alert.objects.create(device=device, alert_type=alert_type,
                                     severity=Alert.SEVERITY_CRITICAL, message=msg)
                logger.warning('CRITICAL alert: %s device=%s value=%.1f', alert_type, device.pk, value)
            elif warn_thr <= value < crit_thr and (alert_type, Alert.SEVERITY_WARNING) not in active_alerts:
                msg = f'{label} kullanımı UYARI seviyesinde: %{value:.1f}'
                Alert.objects.create(device=device, alert_type=alert_type,
                                     severity=Alert.SEVERITY_WARNING, message=msg)
                logger.info('WARNING alert: %s device=%s value=%.1f', alert_type, device.pk, value)

        # COUNT tek seferde: hem anomaly hem cleanup için kullanılır
        total = device.heartbeats.count()

        # Anomali tespiti: her 4. heartbeat'te çalışır (≈1 dakikada bir, 15sn × 4)
        if total % 4 == 0:
            ANOMALY_WINDOW = 20
            ANOMALY_MULTIPLIER = 2.0
            recent_hbs = list(device.heartbeats.exclude(pk=heartbeat.pk).values_list(
                'cpu_percent', 'ram_percent'
            )[:ANOMALY_WINDOW])
            if len(recent_hbs) >= 5:
                cpu_vals = [r[0] for r in recent_hbs]
                ram_vals = [r[1] for r in recent_hbs]
                cpu_base = sum(cpu_vals) / len(cpu_vals)
                ram_base = sum(ram_vals) / len(ram_vals)
                for value, baseline, alert_type, label in [
                    (heartbeat.cpu_percent, cpu_base, 'CPU_ANOMALY', 'CPU'),
                    (heartbeat.ram_percent, ram_base, 'RAM_ANOMALY', 'RAM'),
                ]:
                    if baseline > 5 and value >= baseline * ANOMALY_MULTIPLIER:
                        if (alert_type, Alert.SEVERITY_WARNING) not in active_alerts:
                            msg = (f'{label} ani artış: %{value:.1f} '
                                   f'(son {len(recent_hbs)} ölçüm ort. %{baseline:.1f})')
                            Alert.objects.create(device=device, alert_type=alert_type,
                                                 severity=Alert.SEVERITY_WARNING, message=msg)
                            logger.info('ANOMALY alert: %s device=%s value=%.1f base=%.1f',
                                        alert_type, device.pk, value, baseline)

        # Otomatik temizleme: her CLEANUP_EVERY kayıtta bir eski heartbeat'leri sil
        if total > HEARTBEAT_LIMIT + CLEANUP_EVERY:
            aggregate_completed_hours(device)
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
    mark_stale_devices_inactive()
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


# 13. Saatlik trend verisi (GET) — son 24 saat
@api_view(['GET'])
def device_hourly_trend(request, pk):
    """Bir cihazın son 24 saatlik ortalama metriklerini döndürür.
    Chart.js bar chart bu veriyi kullanarak geçmiş trend grafiği çizer.
    """
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Cihaz bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    since = timezone.now() - timedelta(hours=24)
    rows = list(reversed(list(
        device.hourly_stats.filter(hour__gte=since).order_by('-hour')[:24]
    )))
    data = [{
        'hour': r.hour.strftime('%H:00'),
        'cpu_avg': r.cpu_avg,
        'cpu_max': r.cpu_max,
        'ram_avg': r.ram_avg,
        'ram_max': r.ram_max,
        'disk_avg': r.disk_avg,
        'sample_count': r.sample_count,
    } for r in rows]
    return Response({'device': pk, 'hours': data})


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
    mark_stale_devices_inactive()
    # Correlated subquery: her cihaz için sadece en son heartbeat değerlerini çeker
    # (tüm heartbeat'leri yüklayan Prefetch yerine — çok daha verimli)
    latest_hb = HeartbeatLog.objects.filter(device=OuterRef('pk')).order_by('-timestamp')
    qs = Device.objects.select_related('location', 'hardware').annotate(
        latest_cpu=Subquery(latest_hb.values('cpu_percent')[:1], output_field=FloatField()),
        latest_ram=Subquery(latest_hb.values('ram_percent')[:1], output_field=FloatField()),
    )
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'monitoring/device_list.html', {'devices': page, 'page_obj': page})


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
    qs = Alert.objects.all().order_by('-created_at')
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'monitoring/alert_list.html', {'alerts': page, 'page_obj': page})


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
