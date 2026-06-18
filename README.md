# DevMonitor — Donanım İzleme Sistemi

> Ağdaki bilgisayarların donanım ve performans verilerini gerçek zamanlı olarak merkezi bir web panelinden izleyen sistem. macOS Etkinlik Monitörü seviyesinde detay sunar.

**Geliştirici:** Hamza Hakverir & Yunus Emre Edizer  
**Ders:** Sunucu Taraflı Web Programlama — 2025/2026 Bahar

---

## ✨ Özellikler

| Kategori | Açıklama |
|---|---|
| **Anlık İzleme** | CPU, RAM, Disk, Ağ ve Batarya verileri 15 saniyede bir güncellenir |
| **Çok Cihaz** | Ağdaki tüm bilgisayarlar tek panelden izlenir |
| **Otomatik Kayıt** | Agent çalıştırıldığında cihaz sisteme otomatik kaydolur |
| **Token Güvenliği** | Her cihaza 64 karakterlik benzersiz token — yetkisiz veri gönderimi engellenir |
| **Uyarı Sistemi** | CPU/RAM/Disk eşik aşımında WARNING ve CRITICAL uyarılar otomatik oluşur |
| **Anomali Tespiti** | Her 4 heartbeat'te anlık değer ortalamayı 2× aşarsa ani artış uyarısı verilir |
| **E-posta Bildirimi** | CRITICAL uyarılarda admin e-postası gönderilir (SMTP yapılandırıldığında) |
| **Cihaza Özel Eşikler** | Her cihaz için CPU/RAM/Disk uyarı ve kritik eşikleri ayrı ayarlanabilir |
| **İşlem Takibi** | En çok kaynak kullanan Top 10 uygulama — CPU/RAM/Thread bilgisiyle |
| **Çekirdek Başına CPU** | Her CPU çekirdeğinin kullanım oranı ayrı gösterilir |
| **CPU Sıcaklığı** | Platform destekliyorsa anlık işlemci sıcaklığı izlenir |
| **Disk Bölümleri** | Tüm mount point'lerin doluluk oranı tablo halinde görüntülenir |
| **Ağ Arayüzleri** | NIC bazında gönderilen/alınan veri miktarı |
| **Tag Sistemi** | Cihazlara renkli etiket (Sunucu, Laptop, Masaüstü…) atanabilir |
| **Konum Yönetimi** | Bina / Kat / Oda bilgisi atanabilir |
| **Online/Offline Zaman Çizelgesi** | Son 7 günün online/offline geçişleri günlük çubuk grafiğinde gösterilir |
| **24 Saatlik Trend** | Saatlik ortalama ve maksimum CPU/RAM değerleri bar grafik olarak izlenir |
| **CSV Dışa Aktarım** | Heartbeat ve Alert verileri CSV olarak indirilebilir |
| **Dark / Light Mode** | Tema tercihi localStorage ile kalıcı olarak saklanır |
| **Otomatik Pasifleştirme** | 2 dakika sinyal gelmezse cihaz otomatik "Pasif" olarak işaretlenir |
| **Canlı Özet Mimarisi** | Heartbeat'ler ilişkisel tabloya satır olarak eklenmez; her cihaz `Device.live_metrics` (JSONB) içinde tek satırda güncellenir — bkz. "Canlı Özet & Arşiv Mimarisi" bölümü |
| **Dosya Sistemi Arşivi** | Ham heartbeat geçmişi `archive/<mac>/<tarih>.jsonl` dosyalarında saklanır; CSV export'un yanı sıra hangi günlerin arşivlendiğini listeleyip tek bir günü ham `.jsonl` olarak indirebileceğiniz bir API de var |
| **Windows Servis** | `install_service.py` ile agent Windows servisi olarak kurulabilir; `secure` komutu çökme sonrası otomatik kurtarma + yetkisiz durdurmaya karşı ACL kısıtlaması ekler |
| **Linux Systemd** | `devmonitor.service` ile agent Linux servisi olarak çalıştırılabilir; `ProtectSystem`/`OOMScoreAdjust` gibi sertleştirme ayarlarıyla gelir |
| **Kurulum Sihirbazı** | `setup_agent.py` — hedef bilgisayara agent bağımlılıklarını kurar, sunucu adresini sorar, Windows servisi veya Linux systemd unit'ini otomatik kurup başlatır |

---

## 🛠 Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, Django 5.1.4 |
| REST API | Django REST Framework 3.17 |
| Veritabanı | PostgreSQL (Supabase cloud) |
| Önbellek | Django LocMemCache (in-process, Redis gerektirmez) |
| Arayüz | Django Templates + Bootstrap 5.3 + Chart.js 4.4 |
| İstemci Agent | Python — `psutil`, `requests` |
| Başlatıcı | `baslat.py` (Mac/Linux) · `CALISTIR.bat` (Windows) |

---

## 📁 Proje Yapısı

```
hardware_monitoring_system/
├── core/
│   ├── settings.py          # Tüm ayarlar (.env'den okunur)
│   ├── urls.py              # Ana URL yönlendirme + kök redirect
│   ├── wsgi.py
│   └── asgi.py
├── monitoring/
│   ├── models.py            # 7 model (Device — live_metrics JSONB dahil —,
│   │                        #   HardwareSpec, Alert, Location, Tag,
│   │                        #   DeviceThreshold, DeviceStatusLog)
│   ├── live_stats.py        # Kayan 24 saatlik pencere matematiği (sum/count + bucket eviction)
│   ├── archive.py           # Ham heartbeat'lerin dosya sistemi arşivi (JSONL)
│   ├── tests.py             # live_stats + archive testleri
│   ├── views.py             # API + UI view'lar
│   ├── serializers.py       # DRF serializer'lar (basit + nested)
│   ├── urls.py              # API + UI endpoint'leri
│   ├── admin.py             # Modellerin admin panel kayıtları
│   ├── migrations/          # Migration dosyaları
│   └── templates/monitoring/
│       ├── base.html           # Navbar, dark/light, toast sistemi
│       ├── dashboard.html      # Ana panel — istatistik kartları + grafikler
│       ├── device_list.html    # Cihaz listesi (tag filtresi + sayfalama)
│       ├── device_detail.html  # Cihaz detayı — 6 bölüm + zaman çizelgesi
│       ├── alert_list.html     # Uyarı listesi (sayfalama + çözme)
│       ├── add_alert.html      # Manuel uyarı formu
│       ├── add_location.html   # Konum atama formu
│       ├── threshold_form.html # Cihaza özel eşik ayarları
│       └── manage_tags.html    # Tag oluşturma ve atama
├── agent.py                 # İstemci agent — psutil ile veri toplar + gönderir
├── baslat.py                # Tek komutla başlatıcı (Django + Agent) — geliştirme/demo amaçlı
├── setup_agent.py           # Hedef bilgisayara agent kurulum sihirbazı (Windows/Linux)
├── install_service.py       # Windows servis yükleyici (pywin32) + secure (ACL kısıtlaması)
├── devmonitor.service       # Linux systemd servis dosyası (sertleştirilmiş)
├── devmonitor.plist         # macOS LaunchDaemon şablonu (KeepAlive, root)
├── CALISTIR.bat             # Windows çift tıklama kısayolu
├── manage.py
├── requirements.txt
└── .env                     # Gizli anahtarlar ve DB bilgileri
```

---

## 🗃 Veritabanı Modelleri

### `Device` — Kayıtlı cihazlar
| Alan | Tip | Açıklama |
|---|---|---|
| `mac_address` | CharField (PK) | Birincil anahtar |
| `os_info` | CharField | İşletim sistemi |
| `is_active` | BooleanField | Son 2 dakikada sinyal geldi mi? |
| `last_seen` | DateTimeField | Son heartbeat zamanı |
| `went_online_at` | DateTimeField | Mevcut oturumun başlangıcı |
| `token` | CharField (64) | API kimlik doğrulama tokeni |
| `tags` | M2M → Tag | Atanmış etiketler |
| `heartbeat_count` | IntegerField | Toplam heartbeat sayısı (atomic) |
| `live_metrics` | **JSONField** | Canlı özet — son 10 heartbeat + 24 saatlik kayan ortalama bucket'ları. Detay: "Canlı Özet & Arşiv Mimarisi" bölümü |

### `HardwareSpec` — Statik donanım özellikleri
`cpu_info`, `cpu_cores`, `cpu_threads`, `ram_total`, `vga_info`, `hostname`, `ip_address`

### `Alert` — Sistem uyarıları
`alert_type` · `severity` (WARNING / CRITICAL) · `message` · `is_resolved` · `notified` · `resolution_note` · `resolved_at`

### `DeviceThreshold` — Cihaza özel eşikler
`cpu_warning`, `cpu_critical`, `ram_warning`, `ram_critical`, `disk_warning`, `disk_critical`

### `DeviceStatusLog` — Online/Offline geçiş kayıtları
`went_online` (bool) · `timestamp` — Zaman çizelgesi grafiği bu tablodan beslenir.

### `Tag` — Cihaz etiketleri
`name`, `color` (hex) — Cihazlara M2M ilişkiyle atanır.

### `Location` — Fiziksel konum
`building`, `floor`, `room`

---

## 🧮 Canlı Özet & Arşiv Mimarisi

**Sorun:** Her cihazdan 15sn'de bir gelen heartbeat'i ilişkisel tabloya satır
olarak eklemek (binlerce cihazda) veritabanını kısa sürede kilitler.

**Çözüm — depolamayı ikiye ayırmak:**

| | Ne tutar | Nerede |
|---|---|---|
| **Canlı özet** | Her cihaz **tek satırda** — son 10 ölçüm + 24 saatlik kayan ortalama | `Device.live_metrics` (PostgreSQL **JSONB**) |
| **Ham arşiv** | Geçmişe dönük tüm ölçümler, sadece gerektiğinde okunur | Dosya sistemi — `archive/<mac>/<YYYY-MM-DD>.jsonl` |

Yeni bir heartbeat geldiğinde **satır eklenmez** — `Device` satırının
`live_metrics` hücresi güncellenir (`monitoring/live_stats.py:apply_heartbeat`):

```json
{
  "recent": [ {"...tam heartbeat verisi...", "timestamp": "..."} ],  // en fazla 10 — en eski düşer, yeni sona eklenir (shift)
  "windows": {
    "cpu_percent":  {"sum": 812.4, "count": 34, "buckets": [{"hour": "...", "sum": 41.2, "count": 4, "max": 55.0}, ...]},
    "ram_percent":  { "...": "..." },
    "disk_percent": { "...": "..." }
  }
}
```

### 24 saatlik kayan ortalama matematiği

Tüm satırları toplamak yerine **Sum/Count sayaçları** O(1) güncellenir:

```
Yeni değer v geldiğinde:
    bucket.sum   += v ;  bucket.count   += 1     (v'nin ait olduğu saat bucket'ı)
    window.sum   += v ;  window.count   += 1     (24 saatlik toplam — anında)

24 saatten eski bir bucket pencereden çıkarken:
    window.sum   -= evicted.sum
    window.count -= evicted.count

Ortalama = window.sum / window.count   (her zaman, yeniden taramadan)
```

Bucket'lar 1 saatlik granülerlikte tutulur (sabit boyutlu "circular buffer").
**Takvim günü sıfırlaması yoktur** — pencere gerçek anlamda kayar, böylece gece
yarısı sınırında ortalama aniden sıfırlanıp zıplamaz. Bu matematik
`monitoring/tests.py` içindeki testlerle (200 saatlik simülasyon dahil)
doğrulanmıştır.

### Ham arşiv

`monitoring/archive.py`, her heartbeat'i `archive/<mac-with-dashes>/<tarih>.jsonl`
dosyasına bir satır olarak ekler (append). CSV export ve geçmiş inceleme bu
dosyalardan okunur; canlı dashboard/grafikler asla bu dosyalara dokunmaz.
(MAC adresindeki `:` Windows'ta dosya adında geçersiz olduğu için `-` ile
değiştirilir.)

---

## 🔌 API Endpoint'leri

Base URL: `http://127.0.0.1:8000/api/monitoring/`

### Cihaz (Device)
| Method | URL | Açıklama |
|---|---|---|
| POST | `devices/register/` | Yeni cihaz kaydet / token al |
| GET | `devices/` | Tüm cihazları listele |
| GET | `devices/<mac>/` | Cihaz detayı (nested: konum + donanım + son heartbeat) |
| GET | `devices/<mac>/stats/` | Canlı özetteki son ≤10 heartbeat — Chart.js mini grafik verisi |
| GET | `devices/<mac>/hourly/` | Kayan 24 saatlik ortalama — trend grafik verisi (`live_metrics['windows']`'den) |
| GET | `devices/<mac>/status-log/` | Son 7 günün online/offline geçişleri |

### Heartbeat & Donanım
| Method | URL | Açıklama |
|---|---|---|
| POST | `heartbeats/` | Anlık performans verisi gönder (token gerekir) |
| POST | `hardware/` | Donanım bilgisi gönder / güncelle (token gerekir) |
| GET | `hardware/<mac>/` | Cihaz donanım bilgisini getir |

### Uyarılar (Alert)
| Method | URL | Açıklama |
|---|---|---|
| GET | `alerts/` | Tüm uyarıları listele |
| POST/PATCH | `alerts/<id>/resolve/` | Uyarıyı çözüldü olarak işaretle |

### Dashboard
| Method | URL | Açıklama |
|---|---|---|
| GET | `dashboard/stats/` | Özet istatistikler — AJAX ile 15sn'de bir güncellenir |

### Web Arayüzü (UI)
| URL | Sayfa |
|---|---|
| `ui/dashboard/` | Ana panel |
| `ui/devices/` | Cihaz listesi |
| `ui/devices/<mac>/` | Cihaz detay sayfası |
| `ui/alerts/` | Uyarı listesi |
| `ui/devices/<mac>/threshold/` | Eşik ayarları formu |
| `ui/devices/<mac>/tags/` | Tag yönetimi |
| `ui/devices/<mac>/export/heartbeats/` | Heartbeat CSV indir |
| `ui/alerts/export/` | Alert CSV indir |
| `ui/devices/<mac>/archive/` | Dosya sistemi arşivinde mevcut günleri listele (JSON) |
| `ui/devices/<mac>/archive/<YYYY-MM-DD>/download/` | Belirli bir günün ham `.jsonl` arşiv dosyasını indir |

---

## ⚙️ Kurulum

### 1. Gereksinimleri kur

```bash
pip install -r requirements.txt
```

### 2. `.env` dosyası oluştur

```env
SECRET_KEY=buraya-guclu-rastgele-bir-anahtar-yaz
DEBUG=True

DB_ENGINE=django.db.backends.postgresql
DB_NAME=postgres
DB_USER=kullanici_adi
DB_PASSWORD=sifreniz
DB_HOST=aws-...pooler.supabase.com
DB_PORT=6543
DB_SSLMODE=require

# İsteğe bağlı — CRITICAL uyarılarda e-posta bildirimi
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=you@gmail.com
# EMAIL_HOST_PASSWORD=uygulama-sifresi
# ADMIN_ALERT_EMAIL=admin@ornek.com
```

> Supabase kullanıyorsan `DB_SSLMODE=require` satırını mutlaka ekle.
>
> **`DB_PORT=6543` kullan, `5432` değil.** Supabase pooler'ı (Supavisor) aynı
> host üzerinde iki modda çalışır: `5432` = **Session mode** (sadece ~15
> eşzamanlı bağlantıya izin verir — birden fazla geliştirici/terminal/dev
> server aynı anda bağlanınca `FATAL: max clients reached` hatası verir),
> `6543` = **Transaction mode** (çok daha fazla eşzamanlı istemciyi
> multiplexleyerek destekler, Django uygulamaları için önerilen mod). Bu proje
> bu hatayı 5432 ile gerçekten yaşadı — `.env` dosyanız git'e gitmediği için
> bu değişikliği **her geliştirici kendi `.env`'inde** yapmalı.

### 3. Tabloları oluştur

```bash
python manage.py migrate
```

### 4. Admin kullanıcısı oluştur (isteğe bağlı)

```bash
python manage.py createsuperuser
```

---

## 🚀 Çalıştırma

### Yöntem A — Tek komutla (Mac / Linux)

```bash
python baslat.py
```

Django sunucusu başlar, agent devreye girer, tarayıcı otomatik açılır.

### Yöntem B — Windows

`CALISTIR.bat` dosyasına çift tıkla.

### Yöntem C — Manuel

```bash
# Terminal 1 — Django sunucusu
python manage.py runserver

# Terminal 2 — İzleme ajanı
python agent.py
```

### Yöntem D — Windows Servisi (arka planda, kullanıcıya bağlı değil)

```bash
# Yönetici olarak çalıştır:
python install_service.py install
python install_service.py secure   # kurtarma aksiyonları + ACL kısıtlaması (bkz. aşağıda)
python install_service.py start
```

### Yöntem E — Kurulum Sihirbazı (izlenecek hedef bilgisayara dağıtım için)

Bir bilgisayarı izlemeye almak için bu dosyaları (en azından `agent.py`,
`setup_agent.py`, `install_service.py`, `devmonitor.service`) o makineye
kopyalayıp çalıştırın:

```bash
python setup_agent.py
```

Script sırasıyla: agent bağımlılıklarını (`psutil`, `requests` — **sunucu
bağımlılıkları değil**) kurar, sunucu adresini sorar, platforma göre:
- **Windows** → Windows Servisi (`install_service.py install` + `secure` + `start`)
- **Linux** → systemd unit'i (`/etc/systemd/system/devmonitor.service`, root gerektirir)
- **macOS** → LaunchDaemon (`/Library/LaunchDaemons/com.devmonitor.agent.plist`,
  `devmonitor.plist` şablonundan, `sudo` gerektirir)

kurup başlatır.

### Erişim Adresleri

| Sayfa | URL |
|---|---|
| Dashboard | `http://127.0.0.1:8000/` |
| Cihazlar | `http://127.0.0.1:8000/api/monitoring/ui/devices/` |
| Uyarılar | `http://127.0.0.1:8000/api/monitoring/ui/alerts/` |
| Admin Paneli | `http://127.0.0.1:8000/admin/` |

---

## 🤖 Agent Nasıl Çalışır?

`agent.py` izlenecek her bilgisayarda ayrı çalışır.

**Başlangıç (bir kez):**
1. MAC adresini tespit eder (`uuid.getnode()`)
2. `POST /devices/register/` ile sisteme kaydolur, token alır
3. `POST /hardware/` ile CPU modeli, GPU, RAM, Hostname, IP, çekirdek bilgilerini gönderir

**Döngü (her 15 saniyede bir):**
1. `psutil.cpu_times_percent()` ile CPU sistem/kullanıcı/boş ayrımı
2. Her çekirdek için ayrı kullanım oranı (`percpu=True`)
3. RAM, Swap, Disk I/O, Ağ I/O
4. NIC bazında ağ istatistikleri
5. Tüm disk bölümlerinin doluluk oranı
6. CPU sıcaklığı (platform destekliyorsa)
7. Top 10 CPU/RAM işlemi
8. `POST /heartbeats/` ile tümünü gönderir

**Otomatik yeniden bağlanma:** Sunucuya ulaşamazsa 5-10-20-30-60 saniye bekleyerek tekrar dener.

---

## 📊 Veritabanı İndeksleri

| Tablo | Index | Amaç |
|---|---|---|
| `Alert` | `(is_resolved, created_at DESC)` | Çözülmemiş uyarı sorguları |
| `Alert` | `(device, created_at DESC)` | Cihaza ait uyarı sorguları |
| `Device` | `(is_active, last_seen)` | Pasif cihaz tespiti |
| `DeviceStatusLog` | `(device, timestamp DESC)` | Zaman çizelgesi sorguları |

> Heartbeat/saatlik trend verisi artık ayrı tablolarda değil, `Device.live_metrics`
> (JSONB) içinde — bu sorgular ek index gerektirmeden tek satır okumasıyla gelir.

---

## 🛡️ Agent Çökme Koruması (Client Guard)

### Windows

`install_service.py`, agent.py'yi Windows servisi olarak çalıştırır ve iki katmanlı koruma sağlar:

1. **Süreç seviyesi:** Servis içindeki Python döngüsü, agent.py alt süreci çökerse
   5 saniye içinde yeniden başlatır.
2. **Servis seviyesi (`secure` komutu):** `sc failure` ile SCM'e, servisin
   kendisi (host süreç) çökse bile otomatik yeniden başlatma talimatı verilir;
   `sc sdset` ile servis kontrol ACL'i kısıtlanır — yalnızca **Administrators**
   ve **SYSTEM** servisi başlatıp durdurabilir. Standart/amatör bir kullanıcı
   Görev Yöneticisi, `services.msc` veya `sc stop` ile servisi durduramaz
   ("Access is denied").

Doğrulama: `sc sdshow DevMonitorAgent` ile uygulanan ACL'i, `sc qfailure
DevMonitorAgent` ile kurtarma aksiyonlarını görebilirsiniz.

### Linux

`devmonitor.service`, agent.py'yi bir systemd unit'i olarak çalıştırır:

- **`Restart=always`** — agent.py beklenmedik şekilde (hata koduyla veya temiz
  `exit(0)` ile) kapanırsa yeniden başlatılır. `systemctl stop devmonitor` ile
  kasıtlı durdurma bu davranışı etkilemez.
- **`OOMScoreAdjust=-1000`** — bellek darlığında Linux OOM killer bu süreci
  hedef almaz.
- **`ProtectSystem=strict`, `ProtectHome=read-only`, `NoNewPrivileges=true`** —
  agent.py dosya sistemine yazmadığı için güvenle sandbox'lanabilir.
- **`KillMode=none` kasıtlı olarak KULLANILMADI** — modern systemd'de bu ayar
  orphan (sahipsiz) süreçler bırakabildiği için resmi olarak önerilmiyor;
  varsayılan `KillMode=control-group` korunmuştur.
- **Yetkisiz durdurma koruması:** Bu, sistem genelinde (`--user` değil) bir
  unit olduğu için `systemctl stop devmonitor` çalıştırmak zaten root/sudo veya
  polkit yetkisi gerektirir — ek bir ayara gerek yoktur. Doğrulamak için
  yetkisiz bir oturumdan (sudo OLMADAN) `systemctl stop devmonitor` deneyin;
  "Interactive authentication required" hatası almalısınız.

### macOS

`devmonitor.plist`, agent.py'yi bir **LaunchDaemon** olarak çalıştırır
(`setup_agent.py` ile `/Library/LaunchDaemons/com.devmonitor.agent.plist`'e
kurulur):

- **`KeepAlive=true`** — agent.py ne sebeple kapanırsa kapansın (çökme, normal
  çıkış) launchd onu yeniden başlatır. Linux'taki `Restart=always` / Windows'taki
  `sc failure` ile eşdeğer.
- **LaunchAgent DEĞİL, LaunchDaemon:** LaunchAgent (`~/Library/LaunchAgents`)
  oturum açan kullanıcı olarak çalışır ve o kullanıcı Activity Monitor'den
  serbestçe kapatabilir. LaunchDaemon (`/Library/LaunchDaemons`) **root**
  olarak çalışır — kurmak `sudo` gerektirir, ve standart bir kullanıcı
  `launchctl unload`/Activity Monitor ile durduramaz.
- Doğrulama: `sudo launchctl list | grep devmonitor` ile durumu, yetkisiz bir
  oturumdan (sudo OLMADAN) `launchctl unload /Library/LaunchDaemons/com.devmonitor.agent.plist`
  deneyerek reddedildiğini görebilirsiniz.

---

## 🔒 Güvenlik

- Her cihaz `secrets.token_hex(32)` ile üretilen benzersiz token'a sahiptir
- Heartbeat ve donanım endpoint'leri `Authorization: Token <token>` başlığı olmadan reddedilir
- `SECRET_KEY` `.env`'de tanımlı değilse `DEBUG=True` modunda uyarı verir, `DEBUG=False` modunda **hata fırlatır** (production'a insecure key ile çıkılamaz)
- `DEBUG=True` yalnızca yerel geliştirme içindir
- Production'da `ALLOWED_HOSTS` sunucu domain/IP'siyle güncellenmeli

---

## 📄 Lisans

Akademik proje — Sunucu Taraflı Web Programlama dersi kapsamında geliştirilmiştir.
