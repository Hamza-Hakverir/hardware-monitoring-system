from django.urls import path
from . import views

urlpatterns = [
    # ============================================================
    # API ENDPOINTS — Agent ve frontend tarafından kullanılır
    # ============================================================

    # Cihazlar
    # ⚠️  SIRALAMA ÖNEMLİ: 'register/' sabit URL'si, <str:pk> dinamik URL'sinden
    # ÖNCE gelmelidir. Django URL'leri yukarıdan aşağıya sırayla eşleştirir;
    # sıralama değiştirilirse 'register/' bir MAC adresi gibi işlenip hata verir.
    path('devices/', views.list_devices, name='list_devices'),
    path('devices/register/', views.register_device, name='register_device'),  # ← sabit, önce
    path('devices/<str:pk>/', views.device_detail, name='device_detail'),      # ← dinamik, sonra
    path('devices/<str:pk>/stats/', views.device_stats, name='device_stats'),
    path('devices/<str:pk>/hourly/', views.device_hourly_trend, name='device_hourly_trend'),
    path('devices/<str:pk>/status-log/', views.device_status_log, name='device_status_log'),

    # Heartbeats
    path('heartbeats/', views.receive_heartbeat, name='receive_heartbeat'),

    # Konumlar
    path('locations/', views.list_locations, name='list_locations'),
    path('locations/add/', views.add_location, name='add_location'),

    # Donanım
    path('hardware/', views.update_hardware, name='update_hardware'),
    path('hardware/<str:device_id>/', views.get_hardware, name='get_hardware'),

    # Uyarılar
    path('alerts/', views.list_alerts, name='list_alerts'),
    path('alerts/<int:pk>/resolve/', views.resolve_alert, name='resolve_alert'),

    # Dashboard
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),  # YENİ: Özet veriler

    # ============================================================
    # UI ENDPOINTS — Web arayüzü sayfaları
    # ============================================================
    path('ui/dashboard/', views.dashboard_view, name='ui_dashboard'),        # YENİ: Ana sayfa
    path('ui/devices/', views.device_list_view, name='ui_device_list'),
    path('ui/devices/<str:pk>/', views.device_detail_view, name='ui_device_detail'),  # YENİ: Detay
    path('ui/alerts/', views.alert_list_view, name='ui_alert_list'),
    path('ui/add-location/', views.add_location_view, name='ui_add_location'),
    path('ui/add-alert/', views.add_alert_view, name='ui_add_alert'),
    path('ui/devices/<str:pk>/threshold/', views.device_threshold_view, name='ui_device_threshold'),
    path('ui/devices/<str:pk>/tags/', views.manage_device_tags_view, name='ui_device_tags'),
    path('ui/devices/<str:pk>/export/heartbeats/', views.device_heartbeats_csv, name='ui_heartbeats_csv'),
    path('ui/alerts/export/', views.alerts_csv, name='ui_alerts_csv'),
]
