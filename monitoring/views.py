import csv
import time as _time
import threading
from datetime import timedelta
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Avg, Max, Subquery, OuterRef, FloatField, F
from django.conf import settings
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.cache import cache
import logging

logger = logging.getLogger('monitoring')
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Device, Location, HardwareSpec, HeartbeatLog, Alert, HourlyAggregate,
    DeviceThreshold, DeviceStatusLog, Tag,
)
from .serializers import (
    DeviceSerializer, LocationSerializer, HardwareSpecSerializer,
    HeartbeatLogSerializer, HeartbeatChartSerializer, AlertSerializer,
    DeviceDetailSerializer, DashboardStatsSerializer
)


# ============================================================
# YARDIMCI FONKSİYONLAR — Token doğrulama + e-posta
# ============================================================

def _require_token(request):
    """Authorization: Token <token> header'ını doğrular.
    Başarıda (Device, None), hata durumunda (None, Response) döner.
    """
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Token '):
        return None, Response(
            {'error': 'Authorization header eksik — Token <token> formatında gönderin'},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    token = auth[6:].strip()
    mac = request.data.get('device')
    try:
        return Device.objects.get(mac_address=mac, token=token), None
    except Device.DoesNotExist:
        return None, Response({'error': 'Geçersiz token'}, status=status.HTTP_401_UNAUTHORIZED)


def _send_critical_alert_email(alert):
    """CRITICAL alert için admin'e e-posta gönderir.
    EMAIL_HOST veya ADMIN_ALERT_EMAIL ayarlanmamışsa sessizce atlar.
    """
    if not getattr(settings, 'EMAIL_HOST', '') or not getattr(settings, 'ADMIN_ALERT_EMAIL', ''):
        return False
    try:
        send_mail(
            subject=f'[DevMonitor] KRİTİK Alarm: {alert.alert_type} — {alert.device_id}',
            message=(
                f'Cihaz  : {alert.device_id}\n'
                f'Tür    : {alert.alert_type}\n'
                f'Mesaj  : {alert.message}\n'
                f'Zaman  : {alert.created_at}\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_ALERT_EMAIL],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.error('Alert e-posta gönderilemedi: %s', exc)
        return False


# ============================================================
# YARDIMCI FONKSİYON — Eski cihazları otomatik pasifleştir
# ============================================================
STALE_THRESHOLD_MINUTES = 2  # 2 dakika sinyal gelmezse → pasif
HEARTBEAT_LIMIT = 1440       # Cihaz başına max kayıt (15sn × 1440 = 6 saat)
CLEANUP_EVERY = 96           # Her 96 yeni kayıtta bir temizlik yap (≈24 dakika)
_STALE_CHECK_INTERVAL = 30.0 # Pasifleştirme kontrolü en fazla 30sn'de bir çalışır
_last_stale_check: float = 0.0

def mark_stale_devices_inactive():
    """Son 2 dakikada heartbeat göndermeyen cihazları pasif yapar ve offline log yazar.
    Ardı ardına gelen sayfa yüklerinde gereksiz sorgu yapmaması için 30sn'de bir çalışır.
    """
    global _last_stale_check
    now = _time.monotonic()
    if now - _last_stale_check < _STALE_CHECK_INTERVAL:
        logger.debug('mark_stale_devices_inactive: throttled, skipping (%.1fs ago)', now - _last_stale_check)
        return
    _last_stale_check = now

    cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    going_offline = list(
        Device.objects.filter(is_active=True, last_seen__lt=cutoff)
                      .values_list('mac_address', flat=True)
    )
    if going_offline:
        Device.objects.filter(mac_address__in=going_offline).update(is_active=False)
        DeviceStatusLog.objects.bulk_create([
            DeviceStatusLog(device_id=mac, went_online=False) for mac in going_offline
        ])
        logger.info('mark_stale: %d cihaz pasife alındı: %s', len(going_offline), going_offline)
    else:
        logger.debug('mark_stale: aktif cihaz yok, değişiklik yapılmadı')


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


def _aggregate_background(device):
    """aggregate_completed_hours'ı arka plan thread'inde çalıştırır.
    Heartbeat yanıt süresini bloklamaz; hata olursa loglar.
    """
    try:
        aggregate_completed_hours(device)
        logger.debug('aggregate_completed_hours tamamlandı: %s', device.pk)
    except Exception as exc:
        logger.error('aggregate_completed_hours arka plan hatası [%s]: %s', device.pk, exc)


# ============================================================
# API VIEWS — REST API Endpoint'leri
# ============================================================

# 1. Cihaz kaydı / token alma (POST)
# Yeni cihazda 201 + token döner; zaten kayıtlıysa 200 + token döner.
# Bu endpoint token doğrulaması gerektirmez (ilk kayıt için).
@api_view(['POST'])
def register_device(request):
    mac = request.data.get('mac_address', '').strip()
    os_info = request.data.get('os_info', '')
    if not mac:
        return Response({'error': 'mac_address gerekli'}, status=status.HTTP_400_BAD_REQUEST)

    device, created = Device.objects.get_or_create(
        mac_address=mac,
        defaults={'os_info': os_info},
    )
    if not created and os_info:
        Device.objects.filter(mac_address=mac).update(os_info=os_info)
        device.os_info = os_info

    return Response(
        {'mac_address': device.mac_address, 'token': device.token},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )

# 2. Sinyal (Heartbeat) alma (POST) — Token doğrulaması gerektirir
@api_view(['POST'])
def receive_heartbeat(request):
    _, auth_err = _require_token(request)
    if auth_err:
        return auth_err

    serializer = HeartbeatLogSerializer(data=request.data)
    if serializer.is_valid():
        heartbeat = serializer.save()

        # threshold'u aynı sorguda JOIN ile çek — ayrı lazy-load sorgusu önlenir
        device = Device.objects.select_related('threshold').get(pk=heartbeat.device_id)
        update_fields = ['is_active', 'last_seen']
        was_inactive = not device.is_active
        if was_inactive:
            device.went_online_at = timezone.now()
            update_fields.append('went_online_at')
        device.is_active = True
        device.save(update_fields=update_fields)

        # Online geçişini logla (zaman çizelgesi için)
        if was_inactive:
            DeviceStatusLog.objects.create(device=device, went_online=True)

        # Cihaza özel eşik varsa kullan, yoksa global settings değerlerini kullan
        thr = getattr(device, 'threshold', None)
        gw  = settings.ALERT_WARNING_THRESHOLD
        gc  = settings.ALERT_CRITICAL_THRESHOLD
        metric_checks = [
            (heartbeat.cpu_percent,  'CPU_HIGH',  'CPU',
             thr.cpu_warning  if thr else gw, thr.cpu_critical  if thr else gc),
            (heartbeat.ram_percent,  'RAM_HIGH',  'RAM',
             thr.ram_warning  if thr else gw, thr.ram_critical  if thr else gc),
            (heartbeat.disk_percent, 'DISK_FULL', 'Disk',
             thr.disk_warning if thr else gw, thr.disk_critical if thr else gc),
        ]
        # Mevcut aktif alert'lerin (type, severity) çiftlerini al
        active_alerts = set(
            Alert.objects.filter(device=device, is_resolved=False)
                         .values_list('alert_type', 'severity')
        )
        for value, alert_type, label, warn_thr, crit_thr in metric_checks:
            if value >= crit_thr and (alert_type, Alert.SEVERITY_CRITICAL) not in active_alerts:
                msg = f'{label} kullanımı KRİTİK seviyede: %{value:.1f}'
                new_alert = Alert.objects.create(device=device, alert_type=alert_type,
                                                 severity=Alert.SEVERITY_CRITICAL, message=msg)
                logger.warning('CRITICAL alert: %s device=%s value=%.1f', alert_type, device.pk, value)
                if _send_critical_alert_email(new_alert):
                    new_alert.notified = True
                    new_alert.save(update_fields=['notified'])
            elif warn_thr <= value < crit_thr and (alert_type, Alert.SEVERITY_WARNING) not in active_alerts:
                msg = f'{label} kullanımı UYARI seviyesinde: %{value:.1f}'
                Alert.objects.create(device=device, alert_type=alert_type,
                                     severity=Alert.SEVERITY_WARNING, message=msg)
                logger.info('WARNING alert: %s device=%s value=%.1f', alert_type, device.pk, value)

        # Atomic counter — COUNT(*) yerine tek UPDATE+SELECT (çok daha hızlı)
        Device.objects.filter(pk=device.pk).update(heartbeat_count=F('heartbeat_count') + 1)
        device.refresh_from_db(fields=['heartbeat_count'])
        total = device.heartbeat_count
        logger.debug('heartbeat_count[%s]=%d', device.pk, total)

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
            # aggregate ağır bir GROUP BY — arka planda çalıştır, yanıt süresini bloklamaz
            threading.Thread(
                target=_aggregate_background, args=(device,), daemon=True
            ).start()
            cutoff_ts = device.heartbeats.values_list('timestamp', flat=True)[HEARTBEAT_LIMIT:HEARTBEAT_LIMIT + 1]
            if cutoff_ts:
                device.heartbeats.filter(timestamp__lte=cutoff_ts[0]).delete()
            hourly_cutoff = timezone.now() - timedelta(days=30)
            device.hourly_stats.filter(hour__lt=hourly_cutoff).delete()

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

# 7. Donanım (HardwareSpec) güncelleme (POST) — Token doğrulaması gerektirir
@api_view(['POST'])
def update_hardware(request):
    _, auth_err = _require_token(request)
    if auth_err:
        return auth_err
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
    alert.resolved_at = timezone.now()
    note = (request.data.get('resolution_note') or '').strip()
    if note:
        alert.resolution_note = note
    alert.save(update_fields=['is_resolved', 'resolved_at', 'resolution_note'])
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
    serializer = HeartbeatChartSerializer(heartbeats, many=True)
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
    from django.db.models import Count
    mark_stale_devices_inactive()
    total = Device.objects.count()
    active = Device.objects.filter(is_active=True).count()
    unresolved = Alert.objects.filter(is_resolved=False).count()
    recent = Alert.objects.select_related('device').order_by('-created_at')[:5]

    # Çözülmemiş alertların türe göre dağılımı — dashboard grafiği için
    type_counts = list(
        Alert.objects.filter(is_resolved=False)
        .values('alert_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    data = {
        'total_devices': total,
        'active_devices': active,
        'inactive_devices': total - active,
        'total_alerts': Alert.objects.count(),
        'unresolved_alerts': unresolved,
        'recent_alerts': AlertSerializer(recent, many=True).data,
        'alert_type_counts': type_counts,
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
    """Ana sayfa — Dashboard."""
    from django.db.models import Count
    mark_stale_devices_inactive()

    # Sayısal istatistikler 30sn önbellekte tutulur (6 ayrı sorguyu tekrarlamamak için)
    stats = cache.get('dashboard_stats')
    if stats is None:
        total      = Device.objects.count()
        active     = Device.objects.filter(is_active=True).count()
        unresolved = Alert.objects.filter(is_resolved=False).count()
        alert_type_counts = list(
            Alert.objects.filter(is_resolved=False)
            .values('alert_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        stats = {
            'total_devices':    total,
            'active_devices':   active,
            'inactive_devices': total - active,
            'unresolved_alerts': unresolved,
            'alert_type_counts': alert_type_counts,
        }
        cache.set('dashboard_stats', stats, 30)
        logger.debug('dashboard_stats cache miss — yeniden hesaplandı')
    else:
        logger.debug('dashboard_stats cache hit')

    # recent_alerts + heatmap önbelleğe alınmaz: canlı veri göstermeli
    recent_alerts = list(
        Alert.objects.select_related('device').order_by('-created_at')[:5]
    )
    latest_hb = HeartbeatLog.objects.filter(device=OuterRef('pk')).order_by('-timestamp')
    devices_heatmap = list(
        Device.objects.select_related('hardware').annotate(
            latest_cpu=Subquery(latest_hb.values('cpu_percent')[:1], output_field=FloatField()),
            latest_ram=Subquery(latest_hb.values('ram_percent')[:1], output_field=FloatField()),
        ).order_by('-is_active', 'mac_address')
    )

    context = {
        **stats,
        'recent_alerts':  recent_alerts,
        'devices_heatmap': devices_heatmap,
    }
    return render(request, 'monitoring/dashboard.html', context)


def device_list_view(request):
    """Cihaz listesi sayfası — tag filtresi destekli."""
    mark_stale_devices_inactive()
    selected_tag = request.GET.get('tag', '').strip()
    latest_hb = HeartbeatLog.objects.filter(device=OuterRef('pk')).order_by('-timestamp')
    qs = (
        Device.objects
        .select_related('location', 'hardware')
        .prefetch_related('tags')
        .annotate(
            latest_cpu=Subquery(latest_hb.values('cpu_percent')[:1], output_field=FloatField()),
            latest_ram=Subquery(latest_hb.values('ram_percent')[:1], output_field=FloatField()),
        )
    )
    if selected_tag:
        qs = qs.filter(tags__name=selected_tag).distinct()
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    all_tags = Tag.objects.all().order_by('name')
    return render(request, 'monitoring/device_list.html', {
        'devices': page,
        'page_obj': page,
        'all_tags': all_tags,
        'selected_tag': selected_tag,
    })


def device_detail_view(request, pk):
    """Cihaz detay sayfası — tek cihazın tüm bilgileri + grafikler.
    select_related ile konum ve donanım bilgisi tek sorguyla getirilir.
    prefetch_related ile son heartbeat'ler ve alertler çekilir.
    """
    device = get_object_or_404(Device.objects.prefetch_related('tags'), pk=pk)
    hardware  = getattr(device, 'hardware', None)
    location  = getattr(device, 'location', None)
    threshold = getattr(device, 'threshold', None)
    recent_heartbeats = device.heartbeats.all()[:30]
    recent_alerts     = device.alerts.order_by('-created_at')[:10]
    latest_hb         = device.heartbeats.first()

    context = {
        'device': device,
        'hardware': hardware,
        'location': location,
        'threshold': threshold,
        'recent_heartbeats': recent_heartbeats,
        'recent_alerts': recent_alerts,
        'latest_hb': latest_hb,
    }
    return render(request, 'monitoring/device_detail.html', context)


def alert_list_view(request):
    """Uyarı listesi sayfası."""
    qs = Alert.objects.select_related('device').order_by('-created_at')
    total_count = qs.count()
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'monitoring/alert_list.html', {
        'alerts': page,
        'page_obj': page,
        'total_alert_count': total_count,
    })


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


# ============================================================
# ÖZELLİK 8 — Cihaza özel eşik formu
# ============================================================

def device_threshold_view(request, pk):
    """Cihaza özel alert eşiklerini ayarla / görüntüle."""
    device    = get_object_or_404(Device, pk=pk)
    threshold, _ = DeviceThreshold.objects.get_or_create(device=device)
    errors = []

    if request.method == 'POST':
        try:
            cpu_w  = float(request.POST.get('cpu_warning',  75))
            cpu_c  = float(request.POST.get('cpu_critical', 90))
            ram_w  = float(request.POST.get('ram_warning',  75))
            ram_c  = float(request.POST.get('ram_critical', 90))
            disk_w = float(request.POST.get('disk_warning', 75))
            disk_c = float(request.POST.get('disk_critical', 90))
        except (ValueError, TypeError):
            errors.append('Tüm değerler sayı olmalıdır.')
        else:
            for name, warn, crit in [
                ('CPU', cpu_w, cpu_c),
                ('RAM', ram_w, ram_c),
                ('Disk', disk_w, disk_c),
            ]:
                if not (0 <= warn <= 100 and 0 <= crit <= 100):
                    errors.append(f'{name}: Değerler 0–100 arasında olmalıdır.')
                elif warn >= crit:
                    errors.append(f'{name}: Uyarı eşiği kritik eşikten küçük olmalıdır.')

            if not errors:
                threshold.cpu_warning  = cpu_w
                threshold.cpu_critical = cpu_c
                threshold.ram_warning  = ram_w
                threshold.ram_critical = ram_c
                threshold.disk_warning  = disk_w
                threshold.disk_critical = disk_c
                threshold.save()
                return redirect('ui_device_detail', pk=pk)

    return render(request, 'monitoring/threshold_form.html', {
        'device': device,
        'threshold': threshold,
        'errors': errors,
        'global_warn': settings.ALERT_WARNING_THRESHOLD,
        'global_crit': settings.ALERT_CRITICAL_THRESHOLD,
    })


# ============================================================
# ÖZELLİK 9 — Online/Offline durum logu API
# ============================================================

@api_view(['GET'])
def device_status_log(request, pk):
    """Son 7 günün online/offline geçişlerini döndürür (zaman çizelgesi için)."""
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Cihaz bulunamadı'}, status=status.HTTP_404_NOT_FOUND)

    since = timezone.now() - timedelta(days=7)
    logs  = list(
        device.status_logs
              .filter(timestamp__gte=since)
              .order_by('timestamp')
              .values('went_online', 'timestamp')
    )
    return Response({
        'device': pk,
        'is_currently_active': device.is_active,
        'logs': [
            {'went_online': l['went_online'], 'timestamp': l['timestamp'].isoformat()}
            for l in logs
        ],
    })


# ============================================================
# ÖZELLİK 11 — CSV Dışa Aktarım
# ============================================================

def device_heartbeats_csv(request, pk):
    """Bir cihazın son N heartbeat'ini CSV olarak indirir."""
    device = get_object_or_404(Device, pk=pk)
    try:
        limit = min(max(int(request.GET.get('limit', 100)), 1), 1440)
    except (ValueError, TypeError):
        limit = 100

    fname = f"heartbeats_{pk}_{timezone.now():%Y%m%d_%H%M}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)
    writer.writerow([
        'Zaman', 'CPU %', 'RAM %', 'Disk %',
        'Gönderilen (B)', 'Alınan (B)', 'Süreç', 'Batarya %',
    ])
    for hb in device.heartbeats.all()[:limit]:
        writer.writerow([
            hb.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            hb.cpu_percent,
            hb.ram_percent,
            hb.disk_percent,
            hb.net_bytes_sent,
            hb.net_bytes_recv,
            hb.process_count,
            hb.battery_percent if hb.battery_percent is not None else '',
        ])
    return response


def alerts_csv(request):
    """Alert listesini CSV olarak indirir. ?device=MAC ile cihaza göre filtrele."""
    qs = Alert.objects.select_related('device').order_by('-created_at')
    device_mac = request.GET.get('device', '').strip()
    if device_mac:
        qs = qs.filter(device_id=device_mac)
    try:
        limit = min(max(int(request.GET.get('limit', 1000)), 1), 5000)
    except (ValueError, TypeError):
        limit = 1000

    fname = f"alerts_{device_mac or 'all'}_{timezone.now():%Y%m%d_%H%M}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Cihaz', 'Tür', 'Şiddet', 'Mesaj', 'Çözüldü', 'Tarih'])
    for a in qs[:limit]:
        writer.writerow([
            a.id,
            a.device_id,
            a.alert_type,
            a.severity,
            a.message,
            'Evet' if a.is_resolved else 'Hayır',
            a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    return response


# ============================================================
# ÖZELLİK 12 — Cihaz Etiket Yönetimi
# ============================================================

PRESET_COLORS = [
    ('#0d6efd', 'Mavi'), ('#198754', 'Yeşil'), ('#dc3545', 'Kırmızı'),
    ('#ffc107', 'Sarı'), ('#0dcaf0', 'Cyan'), ('#6f42c1', 'Mor'),
    ('#fd7e14', 'Turuncu'), ('#6c757d', 'Gri'),
]


def manage_device_tags_view(request, pk):
    """Cihaza tag atama / kaldırma + yeni tag oluşturma."""
    device   = get_object_or_404(Device, pk=pk)
    all_tags = Tag.objects.all().order_by('name')
    errors   = []
    success  = ''

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'assign':
            selected_ids = set(request.POST.getlist('tag_ids'))
            valid_ids = set(
                Tag.objects.filter(id__in=selected_ids).values_list('id', flat=True)
            )
            invalid = selected_ids - {str(i) for i in valid_ids}
            if invalid:
                errors.append('Geçersiz tag ID değerleri gönderildi.')
            else:
                device.tags.set(valid_ids)
                success = 'Etiketler kaydedildi.'

        elif action == 'create':
            name  = request.POST.get('tag_name', '').strip()
            color = request.POST.get('tag_color', '#6c757d').strip()
            if not name:
                errors.append('Etiket adı boş olamaz.')
            elif len(name) > 50:
                errors.append('Etiket adı en fazla 50 karakter olabilir.')
            elif not (color.startswith('#') and len(color) == 7):
                errors.append('Geçersiz renk formatı (örn. #ff5733).')
            elif Tag.objects.filter(name__iexact=name).exists():
                errors.append(f'"{name}" etiketi zaten mevcut.')
            else:
                Tag.objects.create(name=name, color=color)
                all_tags = Tag.objects.all().order_by('name')
                success = f'"{name}" etiketi oluşturuldu.'

    device_tag_ids = set(device.tags.values_list('id', flat=True))
    return render(request, 'monitoring/manage_tags.html', {
        'device':       device,
        'all_tags':     all_tags,
        'device_tag_ids': device_tag_ids,
        'preset_colors': PRESET_COLORS,
        'errors':       errors,
        'success':      success,
    })
