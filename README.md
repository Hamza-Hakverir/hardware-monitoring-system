# DevMonitor — Donanım İzleme Sistemi

Ağdaki bilgisayarların donanım ve performans verilerini gerçek zamanlı olarak merkezi bir panelden izleyen web tabanlı sistem. macOS Etkinlik Monitörü seviyesinde detay sunar.

**Geliştirici:** Hamza Hakverir & Yunus Emre Edizer

---

## Özellikler

- **Anlık İzleme** — CPU, RAM, Disk, Ağ ve Batarya verileri 15 saniyede bir güncellenir
- **Çok Cihaz Desteği** — Aynı anda birden fazla bilgisayarı izle
- **Otomatik Kayıt** — Agent çalıştırıldığında cihaz otomatik sisteme kaydolur
- **Otomatik Uyarı** — CPU/RAM/Disk %90'ı geçince uyarı oluşturulur
- **İşlem Takibi** — En çok kaynak kullanan Top 10 uygulama görüntülenir
- **Cihaz Durumu** — 2 dakika sinyal gelmezse cihaz otomatik "Pasif" olarak işaretlenir
- **Konum Yönetimi** — Cihazlara bina/kat/oda bilgisi atanabilir
- **Veri Optimizasyonu** — Cihaz başına 6 saatlik veri tutulur (1440 kayıt), veritabanı dolmaz

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, Django 5.1.4 |
| REST API | Django REST Framework 3.17 |
| Veritabanı | PostgreSQL (Supabase) |
| Arayüz | Django Templates + Bootstrap 5 + Chart.js 4 |
| İstemci Ajan | Python — psutil, requests |
| Başlatıcı | Windows Batch Script |

---

## Proje Yapısı

```
hardware-monitoring-system/
├── core/
│   ├── settings.py          # Veritabanı, uygulama ayarları (.env'den okunur)
│   ├── urls.py              # Ana URL yönlendirme + kök redirect
│   ├── wsgi.py
│   └── asgi.py
├── monitoring/
│   ├── models.py            # 5 model: Device, Location, HardwareSpec, HeartbeatLog, Alert
│   ├── views.py             # 12 API + 6 UI view
│   ├── serializers.py       # DRF serializer'ları (basit + nested)
│   ├── urls.py              # 12 API + 6 UI endpoint
│   ├── admin.py             # Django admin paneli
│   ├── migrations/          # 6 migration dosyası
│   └── templates/monitoring/
│       ├── base.html        # Ana şablon (navbar, Bootstrap, dark/light)
│       ├── dashboard.html   # Ana panel — kartlar + grafikler + AJAX
│       ├── device_list.html # Cihaz listesi
│       ├── device_detail.html  # Cihaz detayı — CPU/RAM/Disk/Ağ grafikleri
│       ├── alert_list.html  # Uyarı listesi
│       ├── add_alert.html   # Manuel uyarı formu
│       └── add_location.html   # Konum atama formu
├── agent.py                 # İstemci ajan — psutil ile veri toplar
├── baslat.py                # Tek tıkla başlatıcı (Django + Agent)
├── CALISTIR.bat             # Windows çift tıklama kısayolu
├── manage.py
├── requirements.txt
└── .env                     # Gizli anahtarlar ve DB bilgileri (git'e ekleme!)
```

---

## Veritabanı Modelleri

### `Device` — Kayıtlı cihazlar
| Alan | Tip | Açıklama |
|---|---|---|
| `mac_address` | CharField (PK) | Birincil anahtar — cihaz kimliği |
| `os_info` | CharField | İşletim sistemi (örn. "Windows 11") |
| `is_active` | BooleanField | Son 2 dakikada sinyal geldi mi? |
| `last_seen` | DateTimeField | Son heartbeat zamanı |
| `created_at` | DateTimeField | İlk kayıt tarihi |

### `HardwareSpec` — Donanım özellikleri (statik)
| Alan | Tip | Açıklama |
|---|---|---|
| `device` | OneToOneField | Bağlı cihaz |
| `cpu_info` | CharField | İşlemci modeli |
| `cpu_cores` | IntegerField | Fiziksel çekirdek sayısı |
| `cpu_threads` | IntegerField | Mantıksal thread sayısı |
| `ram_total` | CharField | Toplam RAM (örn. "15.75 GB") |
| `vga_info` | CharField | Ekran kartı |
| `hostname` | CharField | Bilgisayar adı |
| `ip_address` | CharField | Yerel ağ IP'si |

### `HeartbeatLog` — Anlık performans kayıtları
| Grup | Alanlar |
|---|---|
| Ana metrikler | `cpu_percent`, `ram_percent`, `disk_percent`, `process_count` |
| Batarya | `battery_percent`, `battery_plugged` |
| CPU detay | `cpu_system`, `cpu_user`, `cpu_idle`, `cpu_freq`, `thread_count` |
| Bellek detay | `memory_total`, `memory_used`, `memory_available`, `memory_cached`, `swap_total`, `swap_used` |
| Disk I/O | `disk_read_bytes`, `disk_write_bytes` |
| Ağ | `net_bytes_sent`, `net_bytes_recv`, `net_packets_sent`, `net_packets_recv` |
| İşlemler | `top_processes` (JSON — Top 10 CPU/RAM) |

### `Location` — Fiziksel konum
`building`, `floor`, `room` alanları — cihaza isteğe bağlı atanır.

### `Alert` — Sistem uyarıları
`alert_type` (CPU_HIGH / RAM_HIGH / DISK_FULL), `message`, `is_resolved`, `created_at`

---

## API Endpoint'leri

Base URL: `http://127.0.0.1:8000/api/monitoring/`

| Method | URL | Açıklama |
|---|---|---|
| POST | `devices/register/` | Yeni cihaz kaydet |
| GET | `devices/` | Tüm cihazları listele |
| GET | `devices/<mac>/` | Cihaz detayı (nested) |
| GET | `devices/<mac>/stats/` | Son 30 heartbeat — Chart.js için |
| POST | `heartbeats/` | Anlık performans verisi al |
| POST | `hardware/` | Donanım bilgisi güncelle/ekle |
| GET | `hardware/<mac>/` | Cihaz donanım bilgisi |
| POST | `locations/add/` | Konum ekle |
| GET | `locations/` | Tüm konumlar |
| GET | `alerts/` | Tüm uyarılar |
| POST/PATCH | `alerts/<id>/resolve/` | Uyarıyı çözüldü işaretle |
| GET | `dashboard/stats/` | Dashboard özet — AJAX için |

---

## Kurulum

### 1. Gereksinimleri kur

```bash
pip install -r requirements.txt
```

### 2. `.env` dosyası oluştur

Proje kökünde `.env` dosyası oluştur:

```env
SECRET_KEY=django-insecure-buraya-gizli-anahtar-yaz
DEBUG=True

DB_ENGINE=django.db.backends.postgresql
DB_NAME=postgres
DB_USER=kullanici_adi
DB_PASSWORD=sifreniz
DB_HOST=db.supabase.co
DB_PORT=5432
DB_SSLMODE=require
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

## Çalıştırma

### Yöntem A — Tek tıkla (Windows)

`CALISTIR.bat` dosyasına çift tıkla. Django ve Agent otomatik başlar, tarayıcı açılır.

### Yöntem B — Manuel

```bash
# Terminal 1 — Django sunucusu
python manage.py runserver

# Terminal 2 — İzleme ajanı
python agent.py
```

### Erişim

| Sayfa | URL |
|---|---|
| Dashboard | `http://127.0.0.1:8000/` |
| Cihazlar | `http://127.0.0.1:8000/api/monitoring/ui/devices/` |
| Uyarılar | `http://127.0.0.1:8000/api/monitoring/ui/alerts/` |
| Admin Paneli | `http://127.0.0.1:8000/admin/` |

---

## Agent Nasıl Çalışır?

`agent.py` izlenecek bilgisayarda çalışır. İki aşamalıdır:

**Başlangıç (bir kez):**
1. MAC adresini tespit eder (`uuid.getnode()`)
2. `POST /devices/register/` ile cihazı kaydeder
3. `POST /hardware/` ile CPU/RAM/GPU/IP bilgilerini gönderir

**Döngü (her 15 saniyede bir):**
1. `psutil` ile anlık CPU, RAM, Disk, Ağ, Batarya verisi toplar
2. En çok kaynak kullanan Top 10 işlemi belirler
3. `POST /heartbeats/` ile sunucuya gönderir

---

## Veritabanı İndeksleri

Performans için şu composite index'ler tanımlıdır:

| Tablo | Index | Amaç |
|---|---|---|
| `HeartbeatLog` | `(device, timestamp DESC)` | Dashboard grafik sorguları |
| `Alert` | `(is_resolved, created_at DESC)` | Çözülmemiş uyarı sorguları |
| `Alert` | `(device, created_at DESC)` | Cihaza ait uyarı sorguları |
| `Device` | `(is_active, last_seen)` | Pasif cihaz tespiti |

---

## Güvenlik Notları

- `.env` dosyasını kesinlikle git'e commit etme — `.gitignore`'a ekli olduğundan emin ol
- `DEBUG=True` sadece geliştirme ortamı içindir
- Production'da `ALLOWED_HOSTS`'u sunucu domain/IP'siyle güncelle
- `SECRET_KEY` production'da güçlü rastgele bir değer olmalı
