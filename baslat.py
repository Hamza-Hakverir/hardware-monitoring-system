import os
import socket
import subprocess
import time
import sys
import webbrowser

def print_header():
    print("=====================================================")
    print("🚀 DevMonitor — Donanım İzleme Sistemi Başlatılıyor")
    print("=====================================================")
    print("👨‍💻 Geliştiriciler: Hamza Hakverir & Yunus Emre Edizer\n")

def wait_for_django(host='127.0.0.1', port=8000, timeout=30):
    """Django port 8000'de yanıt verene kadar bekler."""
    print(f"[...] Django hazır olana kadar bekleniyor (max {timeout}sn)...", end='', flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                print(" Hazır!")
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
            print('.', end='', flush=True)
    print(" ZAMAN AŞIMI!")
    return False

def start_services():
    try:
        # Django Sunucusunu Başlat
        print("[1/2] Django Web Sunucusu başlatılıyor...")
        django_process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Django gerçekten ayağa kalkana kadar bekle
        if not wait_for_django():
            django_process.terminate()
            out, _ = django_process.communicate()
            print("\n[HATA] Django başlatılamadı. Sunucu çıktısı:")
            print(out.decode(errors='replace'))
            sys.exit(1)

        # Agent.py'yi Başlat
        print("[2/2] Donanım Veri Toplayıcı (Agent) başlatılıyor...")
        agent_process = subprocess.Popen([sys.executable, "agent.py"])

        print("\n✅ Tüm servisler başarıyla başlatıldı!\n")
        print("🔗 Kısayol Linkleri:")
        print("   - Dashboard: http://127.0.0.1:8000/api/monitoring/ui/dashboard/")
        print("   - Cihazlar : http://127.0.0.1:8000/api/monitoring/ui/devices/")
        print("   - Admin    : http://127.0.0.1:8000/admin/\n")

        print("🌐 Tarayıcı otomatik olarak açılıyor...")
        webbrowser.open("http://127.0.0.1:8000/api/monitoring/ui/dashboard/")

        print("(Çıkış yapmak ve servisleri durdurmak için CTRL+C tuşlarına basabilirsiniz.)\n")

        agent_process.wait()

    except KeyboardInterrupt:
        print("\n\n🛑 Sistem kapatılıyor...")
        django_process.terminate()
        if 'agent_process' in locals():
            agent_process.terminate()
        print("✅ Servisler durduruldu. İyi günler!")
        sys.exit(0)

if __name__ == "__main__":
    print_header()
    start_services()
