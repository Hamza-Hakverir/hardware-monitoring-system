from django.urls import path
from . import views

urlpatterns = [
    # ============================================================
    # API ENDPOINTS — Agent ve frontend tarafından kullanılır
    # ============================================================

    # Cihazlar
    path('devices/', views.list_devices, name='list_devices'),
    path('devices/register/', views.register_device, name='register_device'),
    path('devices/<str:pk>/', views.device_detail, name='device_detail'),
    path('devices/<str:pk>/stats/', views.device_stats, name='device_stats'),  # YENİ: Chart.js verisi

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
]
