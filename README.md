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
| **Veri Optimizasyonu** | Cihaz başına maks 1440 kayıt tutulur; eski veriler saatlik ortalamaya çevrilir |
| **Windows Servis** | `install_service.py` ile agent Windows servisi olarak kurulabilir |
| **Linux Systemd** | `devmonitor.service` ile agent Linux servisi olarak çalıştırılabilir |

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
│   ├── models.py            # 9 model (Device, HardwareSpec, HeartbeatLog,
│   │                        #   Alert, Location, Tag, DeviceThreshold,
│   │                        #   DeviceStatusLog, HourlyAggregate)
│   ├── views.py             # 20 API + UI view (832 satır)
│   ├── serializers.py       # 6 DRF serializer (basit + nested)
│   ├── urls.py              # 20 endpoint (API + UI)
│   ├── admin.py             # 9 modelin tamamı admin panelinde
│   ├── migrations/          # 17 migration dosyası
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
├── baslat.py                # Tek komutla başlatıcı (Django + Agent)
├── install_service.py       # Windows servis yükleyici (pywin32)
├── devmonitor.service       # Linux systemd servis dosyası
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

### `HardwareSpec` — Statik donanım özellikleri
`cpu_info`, `cpu_cores`, `cpu_threads`, `ram_total`, `vga_info`, `hostname`, `ip_address`

### `HeartbeatLog` — Anlık performans kayıtları (15 saniyede bir)
| Grup | Alanlar |
|---|---|
| Ana metrikler | `cpu_percent`, `ram_percent`, `disk_percent`, `process_count` |
| Batarya | `battery_percent`, `battery_plugged` |
| CPU detay | `cpu_system`, `cpu_user`, `cpu_idle`, `cpu_freq`, `thread_count`, `cpu_per_core` (JSON), `cpu_temperature` |
| Bellek detay | `memory_total`, `memory_used`, `memory_available`, `memory_cached`, `swap_total`, `swap_used` |
| Disk I/O | `disk_read_bytes`, `disk_write_bytes`, `disk_partitions` (JSON) |
| Ağ | `net_bytes_sent`, `net_bytes_recv`, `net_packets_sent`, `net_packets_recv`, `net_per_nic` (JSON) |
| İşlemler | `top_processes` (JSON — Top 10 CPU/RAM/Thread) |

### `Alert` — Sistem uyarıları
`alert_type` · `severity` (WARNING / CRITICAL) · `message` · `is_resolved` · `notified` · `resolution_note` · `resolved_at`

### `DeviceThreshold` — Cihaza özel eşikler
`cpu_warning`, `cpu_critical`, `ram_warning`, `ram_critical`, `disk_warning`, `disk_critical`

### `DeviceStatusLog` — Online/Offline geçiş kayıtları
`went_online` (bool) · `timestamp` — Zaman çizelgesi grafiği bu tablodan beslenir.

### `HourlyAggregate` — Saatlik özet
`cpu_avg`, `cpu_max`, `ram_avg`, `ram_max`, `disk_avg`, `sample_count` — 24 saatlik trend grafiği için.

### `Tag` — Cihaz etiketleri
`name`, `color` (hex) — Cihazlara M2M ilişkiyle atanır.

### `Location` — Fiziksel konum
`building`, `floor`, `room`

---

## 🔌 API Endpoint'leri

Base URL: `http://127.0.0.1:8000/api/monitoring/`

### Cihaz (Device)
| Method | URL | Açıklama |
|---|---|---|
| POST | `devices/register/` | Yeni cihaz kaydet / token al |
| GET | `devices/` | Tüm cihazları listele |
| GET | `devices/<mac>/` | Cihaz detayı (nested: konum + donanım + son heartbeat) |
| GET | `devices/<mac>/stats/` | Son 30 heartbeat — Chart.js grafik verisi |
| GET | `devices/<mac>/hourly/` | Son 24 saatlik ortalama — trend grafik verisi |
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
DB_HOST=db.supabase.co
DB_PORT=5432
DB_SSLMODE=require

# İsteğe bağlı — CRITICAL uyarılarda e-posta bildirimi
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=you@gmail.com
# EMAIL_HOST_PASSWORD=uygulama-sifresi
# ADMIN_ALERT_EMAIL=admin@ornek.com
```

> Supabase kullanıyorsan `DB_SSLMODE=require` satırını mutlaka ekle.

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
python install_service.py start
```

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
| `HeartbeatLog` | `(device, timestamp DESC)` | Dashboard grafik sorguları |
| `HourlyAggregate` | `(device, hour DESC)` | 24 saatlik trend sorguları |
| `Alert` | `(is_resolved, created_at DESC)` | Çözülmemiş uyarı sorguları |
| `Alert` | `(device, created_at DESC)` | Cihaza ait uyarı sorguları |
| `Device` | `(is_active, last_seen)` | Pasif cihaz tespiti |
| `DeviceStatusLog` | `(device, timestamp DESC)` | Zaman çizelgesi sorguları |

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
