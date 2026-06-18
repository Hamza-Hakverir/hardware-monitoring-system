from django.contrib import admin
from .models import (
    Device, Location, HardwareSpec, Alert,
    Tag, DeviceThreshold, DeviceStatusLog,
)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('mac_address', 'os_info', 'is_active', 'last_seen', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('mac_address', 'os_info')
    ordering = ('-last_seen',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('device', 'building', 'floor', 'room')
    search_fields = ('device__mac_address', 'building', 'room')


@admin.register(HardwareSpec)
class HardwareSpecAdmin(admin.ModelAdmin):
    list_display = ('device', 'hostname', 'ip_address', 'cpu_info', 'cpu_cores', 'ram_total', 'vga_info', 'last_updated')
    search_fields = ('device__mac_address', 'hostname', 'cpu_info')
    ordering = ('-last_updated',)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('device', 'alert_type', 'severity', 'message', 'is_resolved', 'notified', 'created_at')
    list_filter = ('is_resolved', 'alert_type', 'severity')
    search_fields = ('device__mac_address', 'message')
    ordering = ('-created_at',)
    actions = ['mark_resolved']

    @admin.action(description='Secili uyarilari cozuldu olarak isaretle')
    def mark_resolved(self, request, queryset):
        queryset.update(is_resolved=True)


# ============================================================
# YENİ KAYITLAR — Tag, DeviceThreshold, DeviceStatusLog
# ============================================================

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'cihaz_sayisi')
    search_fields = ('name',)
    ordering = ('name',)

    @admin.display(description='Cihaz Sayısı')
    def cihaz_sayisi(self, obj):
        return obj.devices.count()


@admin.register(DeviceThreshold)
class DeviceThresholdAdmin(admin.ModelAdmin):
    list_display = (
        'device',
        'cpu_warning', 'cpu_critical',
        'ram_warning', 'ram_critical',
        'disk_warning', 'disk_critical',
    )
    search_fields = ('device__mac_address',)
    list_select_related = ('device',)


@admin.register(DeviceStatusLog)
class DeviceStatusLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'durum', 'timestamp')
    list_filter = ('went_online',)
    ordering = ('-timestamp',)
    list_select_related = ('device',)

    @admin.display(description='Durum')
    def durum(self, obj):
        return '🟢 Online' if obj.went_online else '🔴 Offline'

