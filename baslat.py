import os
import subprocess
import time
import sys
import webbrowser

def print_header():
    print("=====================================================")
    print("🚀 DevMonitor — Donanım İzleme Sistemi Başlatılıyor")
    print("=====================================================")
    print("👨‍💻 Geliştiriciler: Hamza Hakverir & Yunus Emre Edizer\n")

def start_services():
    try:
        # Django Sunucusunu Başlat
        print("[1/2] Django Web Sunucusu başlatılıyor...")
        django_process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)  # Sunucunun ayağa kalkması için biraz bekle

        # Agent.py'yi Başlat
        print("[2/2] Donanım Veri Toplayıcı (Agent) başlatılıyor...")
        agent_process = subprocess.Popen(
            [sys.executable, "agent.py"]
            # Çıktıyı gizlemiyoruz ki agent'ın kalp atışlarını görebilelim
        )
        
        print("\n✅ Tüm servisler başarıyla başlatıldı!\n")
        print("🔗 Kısayol Linkleri:")
        print("   - Dashboard: http://127.0.0.1:8000/api/monitoring/ui/dashboard/")
        print("   - Cihazlar : http://127.0.0.1:8000/api/monitoring/ui/devices/")
        print("   - Admin    : http://127.0.0.1:8000/admin/ (admin / admin123)\n")
        
        print("🌐 Tarayıcı otomatik olarak açılıyor...")
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:8000/api/monitoring/ui/dashboard/")
        
        print("\n(Çıkış yapmak ve servisleri durdurmak için CTRL+C tuşlarına basabilirsiniz.)\n")
        
        # Sonsuz döngüde bekle, terminal kapanmasın
        agent_process.wait()

    except KeyboardInterrupt:
        print("\n\n🛑 Sistem kapatılıyor...")
        django_process.terminate()
        agent_process.terminate()
        print("✅ Servisler durduruldu. İyi günler!")
        sys.exit(0)

if __name__ == "__main__":
    print_header()
    start_services()
