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
import argparse

# ============================================================
# AYARLAR (komut satırı argümanları main bloğunda override eder)
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


def get_cpu_temperature():
    """CPU sıcaklığını döndürür. Desteklenmeyen platformlarda None."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Öncelik sırası: coretemp (Linux/Intel), k10temp (AMD), acpitz, cpu-thermal (ARM)
        for key in ('coretemp', 'k10temp', 'acpitz', 'cpu-thermal', 'cpu_thermal'):
            if key in temps:
                entries = temps[key]
                if entries:
                    return round(entries[0].current, 1)
        # Hiçbiri yoksa ilk bulunanı al
        first = next(iter(temps.values()))
        if first:
            return round(first[0].current, 1)
    except (AttributeError, Exception):
        pass
    return None


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

def collect_process_stats(top_count=10):
    """Tüm process'leri tek geçişte toplar.
    Döner: (total_threads, top_count adet süreç listesi)
    """
    all_procs = []
    total_threads = 0
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info', 'num_threads']):
        try:
            info = proc.info
            threads = info['num_threads'] or 0
            total_threads += threads
            mem_mb = round(info['memory_info'].rss / (1024 * 1024), 1) if info['memory_info'] else 0
            all_procs.append({
                'name': info['name'] or 'Bilinmeyen',
                'cpu': info['cpu_percent'] or 0,
                'mem_mb': mem_mb,
                'threads': threads,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    all_procs.sort(key=lambda x: x['cpu'], reverse=True)
    return total_threads, all_procs[:top_count]


# ============================================================
# DETAYLI ANLIK VERİ TOPLAMA — Etkinlik Monitörü Kalitesinde
# ============================================================

def get_realtime_usage():
    """Anlık performans verilerini toplar — Activity Monitor seviyesinde."""

    # --- CPU ---
    cpu_times = psutil.cpu_times_percent(interval=1)
    cpu_freq_obj = psutil.cpu_freq()
    cpu_per_core = psutil.cpu_percent(percpu=True)  # her çekirdek ayrı [%]

    # --- RAM / Bellek ---
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # --- Disk ---
    disk_io = psutil.disk_io_counters()
    disk_parts = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_parts.append({
                    'device': part.device,
                    'mountpoint': part.mountpoint,
                    'fstype': part.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent,
                })
            except (PermissionError, OSError):
                continue
    except Exception:
        pass

    # --- Ağ (toplam + arayüz bazında) ---
    net_io = psutil.net_io_counters()
    net_per_nic: dict = {}
    try:
        for nic, stats in psutil.net_io_counters(pernic=True).items():
            if nic.lower().startswith('lo') or 'loopback' in nic.lower():
                continue
            net_per_nic[nic] = {
                'bytes_sent':   stats.bytes_sent,
                'bytes_recv':   stats.bytes_recv,
                'packets_sent': stats.packets_sent,
                'packets_recv': stats.packets_recv,
            }
    except Exception:
        pass

    # --- Batarya ---
    battery_pct, battery_plug = get_battery_info()

    # --- CPU Sıcaklığı ---
    cpu_temp = get_cpu_temperature()

    # --- İşlemler + Top Listesi (tek geçiş) ---
    pids = psutil.pids()
    total_threads, top_procs = collect_process_stats(10)

    return {
        # Ana metrikler (cpu_times_percent zaten 1sn ölçtü, idle dışı = kullanım)
        "cpu_percent": round(100.0 - cpu_times.idle, 1),
        "ram_percent": mem.percent,
        "disk_percent": psutil.disk_usage('C:\\' if platform.system() == 'Windows' else '/').percent,
        "process_count": len(pids),
        "battery_percent": battery_pct,
        "battery_plugged": battery_plug,

        # CPU detay
        "cpu_system": getattr(cpu_times, 'system', 0),
        "cpu_user": getattr(cpu_times, 'user', 0),
        "cpu_idle": getattr(cpu_times, 'idle', 0),
        "cpu_freq": cpu_freq_obj.current if cpu_freq_obj else 0,
        "thread_count": total_threads,
        "cpu_per_core": cpu_per_core,
        "cpu_temperature": cpu_temp,

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
        "disk_partitions": disk_parts,

        # Ağ
        "net_bytes_sent":   net_io.bytes_sent,
        "net_bytes_recv":   net_io.bytes_recv,
        "net_packets_sent": net_io.packets_sent,
        "net_packets_recv": net_io.packets_recv,
        "net_per_nic":      net_per_nic,

        # Top işlemler (JSON)
        "top_processes": top_procs,
    }


# ============================================================
# API FONKSİYONLARI
# ============================================================

def register_device(info) -> str | None:
    """Cihazı kaydeder / doğrular. Sunucudan dönen token'ı döndürür."""
    payload = {
        "mac_address": info["mac_address"],
        "os_info": info["os_info"],
    }
    delays = [5, 10, 20, 30, 60]
    for attempt, delay in enumerate(delays, start=1):
        try:
            response = requests.post(f"{SERVER_URL}/devices/register/", json=payload, timeout=5)
            if response.status_code == 201:
                data = response.json()
                print(f"[OK] Cihaz kaydedildi. Token: {data.get('token', '')[:8]}…")
                return data.get('token')
            elif response.status_code == 200:
                data = response.json()
                print("[INFO] Bu cihaz zaten kayıtlı. Token alındı.")
                return data.get('token')
            else:
                print(f"[HATA] Kayıt: {response.text}")
                return None
        except requests.exceptions.ConnectionError:
            if attempt < len(delays):
                print(f"[HATA] Sunucuya ulaşılamıyor. {delay}sn sonra tekrar deneniyor... ({attempt}/{len(delays)})")
                time.sleep(delay)
            else:
                print(f"[HATA] Sunucu {len(delays)} denemede de yanıt vermedi. Agent durduruluyor.")
                raise SystemExit(1)
    return None


def send_hardware_spec(info, token: str | None):
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
    headers = {"Authorization": f"Token {token}"} if token else {}
    try:
        response = requests.post(f"{SERVER_URL}/hardware/", json=payload, headers=headers, timeout=5)
        if response.status_code in (200, 201):
            print("[OK] Donanım bilgisi güncellendi.")
        elif response.status_code == 401:
            print("[HATA] Donanım: Geçersiz token — sunucuda token doğrulaması başarısız.")
        else:
            print(f"[HATA] Donanım: {response.text}")
    except requests.exceptions.ConnectionError:
        print("[HATA] Donanım bilgisi gönderilemedi.")


def send_heartbeat(mac_address, token: str | None, usage):
    headers = {"Authorization": f"Token {token}"} if token else {}
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
        "cpu_per_core": usage["cpu_per_core"],
        "cpu_temperature": usage["cpu_temperature"],
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
        "disk_partitions": usage["disk_partitions"],
        # Ağ
        "net_bytes_sent":   usage["net_bytes_sent"],
        "net_bytes_recv":   usage["net_bytes_recv"],
        "net_packets_sent": usage["net_packets_sent"],
        "net_packets_recv": usage["net_packets_recv"],
        "net_per_nic":      usage.get("net_per_nic", {}),
        # Top işlemler
        "top_processes": usage["top_processes"],
    }
    try:
        response = requests.post(f"{SERVER_URL}/heartbeats/", json=payload, headers=headers, timeout=10)
        if response.status_code == 201:
            bat_str = ""
            if usage["battery_percent"] is not None:
                plug = "🔌" if usage["battery_plugged"] else "🔋"
                bat_str = f" | Bat: {plug} {usage['battery_percent']:.0f}%"

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
        elif response.status_code == 401:
            print("[HATA] Heartbeat: Geçersiz token — sunucuya erişim reddedildi.")
        else:
            print(f"[HATA] Heartbeat: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("[HATA] Heartbeat gönderilemedi — sunucu çalışıyor mu?")


# ============================================================
# ANA ÇALIŞMA DÖNGÜSÜ
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevMonitor Donanım İzleme Ajanı")
    parser.add_argument('--server', default=SERVER_URL,
                        help=f'Sunucu adresi (varsayılan: {SERVER_URL})')
    parser.add_argument('--interval', type=int, default=HEARTBEAT_INTERVAL,
                        help=f'Heartbeat aralığı saniye cinsinden (varsayılan: {HEARTBEAT_INTERVAL})')
    parser.add_argument('--token', default=None,
                        help='API token (verilmezse sunucudan otomatik alınır)')
    args = parser.parse_args()
    SERVER_URL = args.server.rstrip('/')
    HEARTBEAT_INTERVAL = args.interval

    print("=" * 60)
    print("  DONANIM İZLEME AJANI v2.0 — Etkinlik Monitörü Modu")
    print("=" * 60)
    print(f"[SUNUCU]   {SERVER_URL}")
    print(f"[ARALIK]   Her {HEARTBEAT_INTERVAL} saniyede bir")

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
    fetched_token = register_device(info)
    token = args.token or fetched_token
    if not token:
        print("[UYARI] Token alınamadı — heartbeat'ler sunucu tarafından reddedilebilir.")
    else:
        print(f"[TOKEN]    {'(argümandan)' if args.token else '(sunucudan)'} {token[:8]}…")

    send_hardware_spec(info, token)
    print("-" * 60)
    print(f"[LOOP] Her {HEARTBEAT_INTERVAL}sn'de bir detaylı veri gönderiliyor...")
    print("[LOOP] Toplanan: CPU+RAM+Disk+Ağ+İşlemler+Batarya")
    print("[LOOP] Durdurmak için CTRL+C")
    print("-" * 60)

    try:
        while True:
            usage = get_realtime_usage()
            send_heartbeat(info["mac_address"], token, usage)
            time.sleep(HEARTBEAT_INTERVAL)
    except KeyboardInterrupt:
        print("\n[STOP] Ajan durduruldu.")
