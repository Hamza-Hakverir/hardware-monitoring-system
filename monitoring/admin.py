from django.contrib import admin
from .models import Device, Location, HardwareSpec, HeartbeatLog, Alert


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


@admin.register(HeartbeatLog)
class HeartbeatLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'cpu_percent', 'ram_percent', 'disk_percent', 'process_count', 'batarya_durumu', 'zaman_damgasi')
    list_filter = ('device',)
    ordering = ('-timestamp',)

    @admin.display(description='Zaman Damgası')
    def zaman_damgasi(self, obj):
        if obj.timestamp:
            return obj.timestamp.strftime('%d %b %Y %H:%M:%S')
        return '-'

    @admin.display(description='Batarya')
    def batarya_durumu(self, obj):
        """Batarya bilgisini ikon ile gösterir"""
        if obj.battery_percent is None:
            return 'Masaüstü'  # Batarya yoksa masaüstü bilgisayar
        plug = '🔌' if obj.battery_plugged else '🔋'
        return f'{plug} %{obj.battery_percent:.0f}'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('device', 'alert_type', 'message', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'alert_type')
    search_fields = ('device__mac_address', 'message')
    ordering = ('-created_at',)
    actions = ['mark_resolved']

    @admin.action(description='Secili uyarilari cozuldu olarak isaretle')
    def mark_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
