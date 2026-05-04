"""
Donanım İzleme Ajanı (Hardware Monitoring Agent) v2.0
=====================================================
macOS Etkinlik Monitörü seviyesinde detaylı veri toplayan agent.

Toplanan Veriler:
    Statik (bir kez):
        - MAC, OS, CPU modeli, GPU, RAM, Hostname, IP, Çekirdek/Thread

    Anlık (her 15 saniyede — Activity Monitor kalitesinde):
        CPU:   Toplam%, Sistem%, Kullanıcı%, Boş%, Frekans, Thread sayısı
        RAM:   Toplam, Kullanılan, Kullanılabilir, Önbellek, Takas
        Disk:  Kullanım%, Okunan/Yazılan byte
        Ağ:    Gönderilen/Alınan byte, Gönderilen/Alınan paket
        Enerji: Batarya%, Şarj durumu
        İşlemler: Süreç sayısı + En çok CPU/RAM kullanan top 10 işlem
"""

import platform
import uuid
import time
import socket
import psutil
import requests
import subprocess
import json

# ============================================================
# AYARLAR
# ============================================================
SERVER_URL = "http://127.0.0.1:8000/api/monitoring"
HEARTBEAT_INTERVAL = 15  # saniye


# ============================================================
# YARDIMCI FONKSİYONLAR — Statik bilgiler (bir kez)
# ============================================================

def get_mac_address():
    mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1])
    return mac.upper()


def get_gpu_info():
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode()
            for line in out.splitlines():
                if "Chipset Model" in line or "Chip" in line:
                    return line.split(":")[-1].strip()
        elif system == "Windows":
            out = subprocess.check_output(
                ["wmic", "path", "win32_videocontroller", "get", "name"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode()
            lines = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != "Name"]
            if lines:
                return lines[0]
        elif system == "Linux":
            out = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL, timeout=5).decode()
            for line in out.splitlines():
                if "VGA" in line:
                    return line.split(":")[-1].strip()
    except Exception:
        pass
    return "Bilinmeyen GPU"


def get_cpu_info():
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode().strip()
            return out
        elif system == "Windows":
            return platform.processor()
        elif system == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[-1].strip()
    except Exception:
        pass
    return platform.processor() or "Bilinmeyen CPU"


def get_hostname():
    return socket.gethostname()


def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Bilinmeyen"


def get_battery_info():
    battery = psutil.sensors_battery()
    if battery is None:
        return None, None
    return battery.percent, battery.power_plugged


def get_system_info():
    return {
        "mac_address": get_mac_address(),
        "os_info": f"{platform.system()} {platform.release()}",
        "cpu_info": get_cpu_info(),
        "ram_total": str(round(psutil.virtual_memory().total / (1024 ** 3), 2)) + " GB",
        "vga_info": get_gpu_info(),
        "hostname": get_hostname(),
        "ip_address": get_ip_address(),
        "cpu_cores": psutil.cpu_count(logical=False) or 0,
        "cpu_threads": psutil.cpu_count(logical=True) or 0,
    }


# ============================================================
# TOP İŞLEMLER — En çok kaynak kullanan 10 uygulama
# ============================================================

def get_top_processes(count=10):
    """En çok CPU ve RAM kullanan top 10 işlemi döndürür.
    Her işlem: {"name": "Safari", "cpu": 12.5, "mem_mb": 387.2, "threads": 8}
    """
    procs = []
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info', 'num_threads']):
        try:
            info = proc.info
            mem_mb = round(info['memory_info'].rss / (1024 * 1024), 1) if info['memory_info'] else 0
            procs.append({
                'name': info['name'] or 'Bilinmeyen',
                'cpu': info['cpu_percent'] or 0,
                'mem_mb': mem_mb,
                'threads': info['num_threads'] or 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # CPU'ya göre sırala, en yüksek ilk
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:count]


# ============================================================
# DETAYLI ANLIK VERİ TOPLAMA — Etkinlik Monitörü Kalitesinde
# ============================================================

def get_realtime_usage():
    """Anlık performans verilerini toplar — Activity Monitor seviyesinde."""

    # --- CPU ---
    cpu_times = psutil.cpu_times_percent(interval=1)
    cpu_freq_obj = psutil.cpu_freq()

    # --- RAM / Bellek ---
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # --- Disk ---
    disk_io = psutil.disk_io_counters()

    # --- Ağ ---
    net_io = psutil.net_io_counters()

    # --- Batarya ---
    battery_pct, battery_plug = get_battery_info()

    # --- İşlemler ---
    pids = psutil.pids()
    total_threads = 0
    for pid in pids:
        try:
            p = psutil.Process(pid)
            total_threads += p.num_threads()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # --- Top İşlemler ---
    top_procs = get_top_processes(10)

    return {
        # Ana metrikler
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": mem.percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "process_count": len(pids),
        "battery_percent": battery_pct,
        "battery_plugged": battery_plug,

        # CPU detay
        "cpu_system": getattr(cpu_times, 'system', 0),
        "cpu_user": getattr(cpu_times, 'user', 0),
        "cpu_idle": getattr(cpu_times, 'idle', 0),
        "cpu_freq": cpu_freq_obj.current if cpu_freq_obj else 0,
        "thread_count": total_threads,

        # Bellek detay
        "memory_total": mem.total,
        "memory_used": mem.used,
        "memory_available": mem.available,
        "memory_cached": getattr(mem, 'cached', 0) or getattr(mem, 'inactive', 0),
        "swap_total": swap.total,
        "swap_used": swap.used,

        # Disk I/O
        "disk_read_bytes": disk_io.read_bytes if disk_io else 0,
        "disk_write_bytes": disk_io.write_bytes if disk_io else 0,

        # Ağ
        "net_bytes_sent": net_io.bytes_sent,
        "net_bytes_recv": net_io.bytes_recv,
        "net_packets_sent": net_io.packets_sent,
        "net_packets_recv": net_io.packets_recv,

        # Top işlemler (JSON)
        "top_processes": top_procs,
    }


# ============================================================
# API FONKSİYONLARI
# ============================================================

def register_device(info):
    payload = {
        "mac_address": info["mac_address"],
        "os_info": info["os_info"],
        "is_active": True,
    }
    try:
        response = requests.post(f"{SERVER_URL}/devices/register/", json=payload, timeout=5)
        if response.status_code == 201:
            print("[OK] Cihaz başarıyla kaydedildi.")
        elif response.status_code == 400 and "mac_address" in response.text:
            print("[INFO] Bu cihaz zaten sistemde kayıtlı.")
        else:
            print(f"[HATA] Kayıt: {response.text}")
    except requests.exceptions.ConnectionError:
        print("[HATA] Sunucuya ulaşılamıyor! Django runserver çalışıyor mu?")
        raise SystemExit(1)


def send_hardware_spec(info):
    payload = {
        "device": info["mac_address"],
        "cpu_info": info["cpu_info"],
        "ram_total": info["ram_total"],
        "vga_info": info["vga_info"],
        "hostname": info["hostname"],
        "ip_address": info["ip_address"],
        "cpu_cores": info["cpu_cores"],
        "cpu_threads": info["cpu_threads"],
    }
    try:
        response = requests.post(f"{SERVER_URL}/hardware/", json=payload, timeout=5)
        if response.status_code in (200, 201):
            print("[OK] Donanım bilgisi güncellendi.")
        else:
            print(f"[HATA] Donanım: {response.text}")
    except requests.exceptions.ConnectionError:
        print("[HATA] Donanım bilgisi gönderilemedi.")


def send_heartbeat(mac_address, usage):
    payload = {
        "device": mac_address,
        # Ana
        "cpu_percent": usage["cpu_percent"],
        "ram_percent": usage["ram_percent"],
        "disk_percent": usage["disk_percent"],
        "process_count": usage["process_count"],
        "battery_percent": usage["battery_percent"],
        "battery_plugged": usage["battery_plugged"],
        # CPU detay
        "cpu_system": usage["cpu_system"],
        "cpu_user": usage["cpu_user"],
        "cpu_idle": usage["cpu_idle"],
        "cpu_freq": usage["cpu_freq"],
        "thread_count": usage["thread_count"],
        # Bellek detay
        "memory_total": usage["memory_total"],
        "memory_used": usage["memory_used"],
        "memory_available": usage["memory_available"],
        "memory_cached": usage["memory_cached"],
        "swap_total": usage["swap_total"],
        "swap_used": usage["swap_used"],
        # Disk
        "disk_read_bytes": usage["disk_read_bytes"],
        "disk_write_bytes": usage["disk_write_bytes"],
        # Ağ
        "net_bytes_sent": usage["net_bytes_sent"],
        "net_bytes_recv": usage["net_bytes_recv"],
        "net_packets_sent": usage["net_packets_sent"],
        "net_packets_recv": usage["net_packets_recv"],
        # Top işlemler
        "top_processes": usage["top_processes"],
    }
    try:
        response = requests.post(f"{SERVER_URL}/heartbeats/", json=payload, timeout=10)
        if response.status_code == 201:
            bat_str = ""
            if usage["battery_percent"] is not None:
                plug = "🔌" if usage["battery_plugged"] else "🔋"
                bat_str = f" | Bat: {plug}%{usage['battery_percent']:.0f}"

            mem_gb = usage['memory_used'] / (1024**3)
            net_mb = usage['net_bytes_recv'] / (1024**2)

            print(
                f"[OK] CPU: %{usage['cpu_percent']:.1f} "
                f"(Sys:{usage['cpu_system']:.1f} Usr:{usage['cpu_user']:.1f} Boş:{usage['cpu_idle']:.1f}) | "
                f"RAM: %{usage['ram_percent']:.1f} ({mem_gb:.1f}GB) | "
                f"Disk: %{usage['disk_percent']:.1f} | "
                f"Süreç: {usage['process_count']} | "
                f"Thread: {usage['thread_count']} | "
                f"Ağ: ↓{net_mb:.0f}MB"
                f"{bat_str}"
            )
        else:
            print(f"[HATA] Heartbeat: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("[HATA] Heartbeat gönderilemedi — sunucu çalışıyor mu?")


# ============================================================
# ANA ÇALIŞMA DÖNGÜSÜ
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  DONANIM İZLEME AJANI v2.0 — Etkinlik Monitörü Modu")
    print("=" * 60)

    info = get_system_info()
    print(f"[MAC]      {info['mac_address']}")
    print(f"[HOST]     {info['hostname']}")
    print(f"[IP]       {info['ip_address']}")
    print(f"[OS]       {info['os_info']}")
    print(f"[CPU]      {info['cpu_info']}")
    print(f"[Çekirdek] {info['cpu_cores']} çekirdek / {info['cpu_threads']} thread")
    print(f"[RAM]      {info['ram_total']}")
    print(f"[GPU]      {info['vga_info']}")

    bat_pct, bat_plug = get_battery_info()
    if bat_pct is not None:
        print(f"[Batarya]  %{bat_pct:.0f} — {'Şarjda ✓' if bat_plug else 'Pilde ✗'}")
    else:
        print("[Batarya]  Yok (Masaüstü)")

    print("-" * 60)
    register_device(info)
    send_hardware_spec(info)
    print("-" * 60)
    print(f"[LOOP] Her {HEARTBEAT_INTERVAL}sn'de bir detaylı veri gönderiliyor...")
    print("[LOOP] Toplanan: CPU+RAM+Disk+Ağ+İşlemler+Batarya")
    print("[LOOP] Durdurmak için CTRL+C")
    print("-" * 60)

    try:
        while True:
            usage = get_realtime_usage()
            send_heartbeat(info["mac_address"], usage)
            time.sleep(HEARTBEAT_INTERVAL)
    except KeyboardInterrupt:
        print("\n[STOP] Ajan durduruldu.")
