"""
DevMonitor Agent Kurulum Sihirbazı
====================================
İzlenecek hedef bilgisayara (Windows / Linux / macOS) agent.py'yi kurar ve
arka planda sürekli çalışacak şekilde yapılandırır:
    - Windows  → install_service.py üzerinden Windows Servisi (+ secure: çökme
                 koruması ve yetki kısıtlaması)
    - Linux    → devmonitor.service şablonundan systemd unit'i kurar
    - macOS    → devmonitor.plist şablonundan LaunchDaemon kurar (root, KeepAlive)

Bu script SADECE agent.py'nin bağımlılıklarını (psutil, requests) kurar —
Django/DRF/psycopg2 gibi sunucu bağımlılıkları (requirements.txt) hedef
bilgisayara KURULMAZ, çünkü bu makine sadece veri gönderen bir ajan, sunucu
değildir.

Kullanım:
    python setup_agent.py
"""
import os
import platform
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM = platform.system()  # 'Windows' | 'Linux' | 'Darwin'
DEFAULT_SERVER_URL = "http://127.0.0.1:8000/api/monitoring"


def _run(cmd):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd)


def install_dependencies():
    print("[1/3] Agent bağımlılıkları kuruluyor (psutil, requests)...")
    result = _run([sys.executable, "-m", "pip", "install", "--quiet", "psutil", "requests"])
    if result.returncode != 0:
        print("[HATA] Bağımlılıklar kurulamadı.")
        sys.exit(1)
    print("[OK] Bağımlılıklar hazır.")


def ask_server_url():
    url = input(f"Sunucu adresi [{DEFAULT_SERVER_URL}]: ").strip()
    return url or DEFAULT_SERVER_URL


def setup_windows(server_url):
    installer = os.path.join(THIS_DIR, "install_service.py")

    # agent.py'ye --server argümanını iletmek için install_service.py'nin
    # okuduğu service_args.txt dosyasına yazılır (bkz. install_service.py).
    args_file = os.path.join(THIS_DIR, "service_args.txt")
    with open(args_file, "w", encoding="utf-8") as f:
        f.write(f"--server {server_url}")
    print(f"[OK] Servis argümanları yazıldı: --server {server_url}")

    print("\n[2/3] Windows Servisi kuruluyor (yönetici yetkisi gerektirir)...")
    if _run([sys.executable, installer, "install"]).returncode != 0:
        print("[HATA] Servis kurulamadı — bu terminali 'Yönetici olarak çalıştır' ile açıp tekrar deneyin.")
        sys.exit(1)

    print("\n[3/3] Çökme koruması + yetki kısıtlaması uygulanıyor (secure) ve servis başlatılıyor...")
    _run([sys.executable, installer, "secure"])
    _run([sys.executable, installer, "start"])

    print("\n[OK] Kurulum tamamlandı.")
    print("     Durum kontrolü : python install_service.py status")
    print("     ACL doğrulama  : sc sdshow DevMonitorAgent")


def setup_linux(server_url):
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("[HATA] Linux'ta systemd servisi kurmak için root yetkisi gerekir.")
        print(f"       Tekrar deneyin: sudo {sys.executable} {os.path.abspath(__file__)}")
        sys.exit(1)

    template_path = os.path.join(THIS_DIR, "devmonitor.service")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()

    agent_path = os.path.join(THIS_DIR, "agent.py")
    content = content.replace("WorkingDirectory=/opt/devmonitor", f"WorkingDirectory={THIS_DIR}")
    content = content.replace(
        "ExecStart=/usr/bin/python3 /opt/devmonitor/agent.py",
        f"ExecStart={sys.executable} {agent_path} --server {server_url}",
    )

    dest = "/etc/systemd/system/devmonitor.service"
    print(f"\n[2/3] systemd unit dosyası yazılıyor: {dest}")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)

    print("\n[3/3] Servis etkinleştiriliyor ve başlatılıyor...")
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "enable", "--now", "devmonitor"])

    print("\n[OK] Kurulum tamamlandı.")
    print("     Durum kontrolü : systemctl status devmonitor")
    print("     Loglar         : journalctl -u devmonitor -f")
    print("     Yetkisiz durdurma denemesi (sudo OLMADAN): systemctl stop devmonitor → reddedilmeli")


def setup_macos(server_url):
    # LaunchDaemon (LaunchAgent DEĞİL) kasıtlı: root olarak çalışır, sadece admin
    # yetkili kullanıcı durdurabilir — bkz. devmonitor.plist içindeki not.
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("[HATA] macOS'ta LaunchDaemon kurmak için root yetkisi gerekir")
        print("       (bu sayede amatör bir kullanıcı Activity Monitor'den kapatamaz).")
        print(f"       Tekrar deneyin: sudo {sys.executable} {os.path.abspath(__file__)}")
        sys.exit(1)

    agent_path = os.path.join(THIS_DIR, "agent.py")
    log_path = os.path.join(THIS_DIR, "devmonitor.log")
    template_path = os.path.join(THIS_DIR, "devmonitor.plist")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()

    content = (
        content.replace("__PYTHON_EXE__", sys.executable)
               .replace("__AGENT_PATH__", agent_path)
               .replace("__SERVER_URL__", server_url)
               .replace("__WORKDIR__", THIS_DIR)
               .replace("__LOG_PATH__", log_path)
    )

    dest = "/Library/LaunchDaemons/com.devmonitor.agent.plist"
    print(f"\n[2/3] LaunchDaemon dosyası yazılıyor: {dest}")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    _run(["chown", "root:wheel", dest])
    _run(["chmod", "644", dest])

    print("\n[3/3] Servis yükleniyor ve başlatılıyor...")
    _run(["launchctl", "load", "-w", dest])

    print("\n[OK] Kurulum tamamlandı.")
    print("     Durum kontrolü : sudo launchctl list | grep devmonitor")
    print(f"     Loglar         : tail -f {log_path}")
    print(f"     Yetkisiz durdurma denemesi (sudo OLMADAN): launchctl unload {dest} → reddedilmeli")


def main():
    print("=" * 60)
    print("  DevMonitor Agent Kurulum Sihirbazı")
    print(f"  Platform: {SYSTEM}")
    print("=" * 60)

    install_dependencies()
    server_url = ask_server_url()
    print()

    if SYSTEM == "Windows":
        setup_windows(server_url)
    elif SYSTEM == "Linux":
        setup_linux(server_url)
    elif SYSTEM == "Darwin":
        setup_macos(server_url)
    else:
        print(f"[HATA] Desteklenmeyen platform: {SYSTEM}")
        sys.exit(1)


if __name__ == "__main__":
    main()
