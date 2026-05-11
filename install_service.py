"""
DevMonitor Windows Servis Yükleyici
====================================
Gereksinim: pip install pywin32

Kullanım (Yönetici olarak çalıştır):
    python install_service.py install   — servisi yükle
    python install_service.py start     — servisi başlat
    python install_service.py stop      — servisi durdur
    python install_service.py restart   — servisi yeniden başlat
    python install_service.py remove    — servisi kaldır
    python install_service.py status    — servis durumunu göster
    python install_service.py debug     — ön planda çalıştır (test için)
"""

import sys
import os
import subprocess
import time

SERVICE_NAME    = "DevMonitorAgent"
SERVICE_DISPLAY = "DevMonitor Donanım İzleme Ajanı"
SERVICE_DESC    = "Cihaz metriklerini (CPU, RAM, Disk, Ağ) periyodik olarak DevMonitor sunucusuna gönderir."

# Agent ve Python yolunu otomatik bul
THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
AGENT_PATH = os.path.join(THIS_DIR, "agent.py")
PYTHON_EXE = sys.executable  # Bu scripti çalıştıran Python


# ============================================================
# Windows Servis Sınıfı (pywin32)
# ============================================================

try:
    import win32serviceutil
    import win32service
    import win32event
    import win32process
    import servicemanager
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False


if HAS_PYWIN32:
    class DevMonitorService(win32serviceutil.ServiceFramework):
        _svc_name_        = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._process    = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            self._run()

        def _run(self):
            cmd = [PYTHON_EXE, AGENT_PATH]
            while True:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=THIS_DIR,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                # Agent biterse ya da stop sinyali gelirse döngüden çık
                while self._process.poll() is None:
                    result = win32event.WaitForSingleObject(self._stop_event, 2000)
                    if result == win32event.WAIT_OBJECT_0:
                        return  # SvcStop çağrıldı
                # Agent beklenmedik şekilde çıktıysa 5sn bekle ve yeniden başlat
                rc = self._process.returncode
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_WARNING_TYPE,
                    servicemanager.PYS_SERVICE_STOPPED,
                    (self._svc_name_, f" (agent exit code {rc}, restarting in 5s)"),
                )
                result = win32event.WaitForSingleObject(self._stop_event, 5000)
                if result == win32event.WAIT_OBJECT_0:
                    return


# ============================================================
# Yardımcı komutlar — pywin32 gerekmez
# ============================================================

def _sc(args):
    """sc.exe veya net.exe komutunu çalıştır ve çıktıyı yazdır."""
    result = subprocess.run(args, capture_output=True, text=True)
    out = (result.stdout + result.stderr).strip()
    if out:
        print(out)
    return result.returncode


def cmd_status():
    print(f"\n[Servis: {SERVICE_NAME}]")
    _sc(["sc", "query", SERVICE_NAME])


def cmd_debug():
    """Servisi doğrudan ön planda çalıştır — Ctrl+C ile durdurun."""
    print(f"[DEBUG] Agent başlatılıyor: {AGENT_PATH}")
    try:
        subprocess.run([PYTHON_EXE, AGENT_PATH], cwd=THIS_DIR)
    except KeyboardInterrupt:
        print("\n[DEBUG] Durduruldu.")


# ============================================================
# Giriş noktası
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    action = sys.argv[1].lower()

    if action == "debug":
        cmd_debug()
        return

    if action == "status":
        cmd_status()
        return

    if not HAS_PYWIN32:
        print("[HATA] pywin32 yüklü değil.")
        print("       pip install pywin32")
        print("       python -m pywin32_postinstall -install")
        sys.exit(1)

    if action in ("install", "update", "remove", "start", "stop", "restart"):
        # install/remove için yönetici yetkisi gerekli
        win32serviceutil.HandleCommandLine(DevMonitorService)
    else:
        print(f"[HATA] Bilinmeyen komut: {action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
