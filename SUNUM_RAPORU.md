# DevMonitor — Donanım İzleme Sistemi
## Proje Sunum Raporu

**Geliştirici:** Hamza Hakverir & Yunus Emre Edizer  
**Tarih:** Mayıs 2026  
**Platform:** Web Tabanlı (Python / Django)

---

## 1. Projenin Amacı ve Kapsamı

DevMonitor, bir ağdaki bilgisayarların donanım ve anlık performans bilgilerini merkezi bir web panelinden gerçek zamanlı olarak izlemek amacıyla geliştirilmiş bir sistem izleme uygulamasıdır.

Proje; **sunucu tarafı (backend)**, **web arayüzü (frontend)** ve **istemci tarafında çalışan bir ajan (agent)** olmak üzere üç ana bileşenden oluşmaktadır.

### Çözülen Problem

Birden fazla bilgisayarın bulunduğu ortamlarda (laboratuvar, ofis, okul) her cihazın durumunu tek tek kontrol etmek zaman alıcıdır. DevMonitor, bu cihazların tamamının CPU, RAM, disk, ağ ve batarya verilerini tek bir ekrandan anlık olarak takip etmeyi mümkün kılar.

---

## 2. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────┐
│                    İzlenen Bilgisayarlar                │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │  agent.py    │   │  agent.py    │   │  agent.py   │ │
│  │  (Cihaz 1)   │   │  (Cihaz 2)   │   │  (Cihaz N)  │ │
│  └──────┬───────┘   └──────┬───────┘   └──────┬──────┘ │
└─────────┼─────────────────┼──────────────────┼─────────┘
          │  HTTP POST       │                  │
          │  (her 15 sn)     │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                   Django REST API Sunucusu              │
│                  (Django 5.1 + DRF 3.17)               │
│                                                         │
│   /devices/register/    /heartbeats/    /alerts/        │
│   /hardware/            /dashboard/stats/               │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL Veritabanı (Supabase)            │
│   Device │ HardwareSpec │ HeartbeatLog │ Alert │ Location│
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     Web Arayüzü                         │
│   Dashboard │ Cihaz Listesi │ Cihaz Detayı │ Uyarılar  │
│   Bootstrap 5 + Chart.js + AJAX (15sn auto-refresh)     │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Kullanılan Teknolojiler

### Backend
| Teknoloji | Sürüm | Kullanım Amacı |
|---|---|---|
| Python | 3.12 | Ana programlama dili |
| Django | 5.1.4 | Web framework, ORM, Admin paneli |
| Django REST Framework | 3.17.1 | REST API katmanı |
| psycopg2-binary | 2.9.11 | PostgreSQL bağlantı sürücüsü |
| python-dotenv | 1.2.2 | Ortam değişkeni yönetimi |

### Agent (İstemci)
| Teknoloji | Kullanım Amacı |
|---|---|
| psutil 6.0 | CPU, RAM, Disk, Ağ, Batarya verisi toplama |
| requests 2.32 | HTTP ile sunucuya veri gönderme |
| platform / socket / uuid | Sistem bilgisi ve MAC adresi tespiti |

### Frontend
| Teknoloji | Kullanım Amacı |
|---|---|
| Bootstrap 5 | Responsive arayüz bileşenleri |
| Chart.js 4.4 | Gerçek zamanlı grafikler |
| Bootstrap Icons | İkonlar |
| Vanilla JS + Fetch API | AJAX ile otomatik yenileme |

### Altyapı
| Teknoloji | Kullanım Amacı |
|---|---|
| PostgreSQL (Supabase) | Bulut veritabanı |
| Git | Sürüm kontrolü |

---

## 4. Veritabanı Tasarımı

Sistem **5 model** üzerine inşa edilmiştir:

```
Device (MAC adresi PK)
  │
  ├── HardwareSpec [1:1]  → CPU, RAM, GPU, IP, Hostname
  ├── Location [1:1]      → Bina, Kat, Oda
  ├── HeartbeatLog [1:N]  → Anlık performans kayıtları
  └── Alert [1:N]         → Sistem uyarıları
```

### HeartbeatLog — En Kritik Model

Her 15 saniyede bir kayıt oluşturulur. Tek bir satırda **27 farklı ölçüm** saklanır:

- **CPU:** Toplam%, Sistem%, Kullanıcı%, Boş%, Frekans (MHz), Thread sayısı
- **Bellek:** Kullanılan, Kullanılabilir, Önbellekteki, Swap (byte cinsinden)
- **Disk:** Kullanım%, Okunan/Yazılan byte (toplam)
- **Ağ:** Gönderilen/Alınan byte ve paket sayısı
- **Batarya:** Yüzde ve şarj durumu
- **İşlemler:** Top 10 uygulama (JSON — isim, CPU%, RAM MB)

### Performans Optimizasyonları

| Sorgu | İndeks |
|---|---|
| Cihaza ait son heartbeat'ler | `(device_id, timestamp DESC)` |
| Çözülmemiş uyarılar | `(is_resolved, created_at DESC)` |
| Cihaza ait uyarılar | `(device_id, created_at DESC)` |
| Pasif cihaz tespiti | `(is_active, last_seen)` |

**Veri saklama politikası:** Cihaz başına maksimum 1440 kayıt (= 6 saatlik veri). Her ~24 dakikada bir otomatik temizleme çalışır. Supabase ücretsiz katman (500MB) hiçbir zaman dolmaz.

---

## 5. REST API Tasarımı

Sistem **12 API endpoint**'i sunar. Agent ve JavaScript AJAX istekleri bu endpoint'leri kullanır.

### Cihaz Yönetimi
```
POST   /api/monitoring/devices/register/     → Cihaz kaydı
GET    /api/monitoring/devices/              → Tüm cihazlar
GET    /api/monitoring/devices/<mac>/        → Tek cihaz (nested)
GET    /api/monitoring/devices/<mac>/stats/  → Grafik verisi (kronolojik)
```

### Veri Akışı
```
POST   /api/monitoring/heartbeats/           → Anlık performans verisi
POST   /api/monitoring/hardware/             → Donanım bilgisi
GET    /api/monitoring/dashboard/stats/      → Dashboard özeti (AJAX)
```

### Uyarı Yönetimi
```
GET    /api/monitoring/alerts/               → Tüm uyarılar
POST   /api/monitoring/alerts/<id>/resolve/  → Uyarı kapat
```

---

## 6. Agent Çalışma Mantığı

Agent (`agent.py`), izlenecek her bilgisayarda çalıştırılan bağımsız bir Python betiğidir.

### Başlangıç Süreci (Bir Kez)

```
agent.py başlar
    │
    ├─ MAC adresi tespit et (uuid.getnode())
    ├─ IP, hostname, işletim sistemi bilgisi topla
    ├─ CPU modeli (wmic / sysctl / /proc/cpuinfo)
    ├─ GPU bilgisi (wmic / system_profiler / lspci)
    │
    ├─ POST /devices/register/   → Cihazı kaydet (zaten varsa hata yok)
    └─ POST /hardware/           → Donanım bilgilerini gönder
```

### Döngü (Her 15 Saniyede Bir)

```
get_realtime_usage() çağrılır
    │
    ├─ cpu_times_percent(interval=1)  → 1 saniye ölçüm (cpu_system, cpu_user, cpu_idle)
    ├─ cpu_percent = 100 - cpu_idle   → Toplam CPU kullanımı
    ├─ virtual_memory()               → RAM metrikleri
    ├─ disk_io_counters()             → Disk okuma/yazma
    ├─ net_io_counters()              → Ağ trafiği
    ├─ sensors_battery()              → Batarya (varsa)
    ├─ process_iter()                 → Top 10 CPU kullanan uygulama
    │
    └─ POST /heartbeats/  → Tüm veriyi sunucuya gönder
```

**Çapraz platform:** Windows, macOS ve Linux'ta çalışır. GPU ve CPU bilgisi her işletim sistemi için ayrı komutla alınır.

---

## 7. Web Arayüzü

### Dashboard (Ana Sayfa)

- **4 özet kart:** Toplam cihaz / Aktif / Pasif / Bekleyen uyarı
- **Doughnut grafik:** Aktif-pasif cihaz oranı
- **Bar grafik:** Son uyarı türleri (CPU_HIGH, RAM_HIGH, DISK_FULL)
- **Uyarı tablosu:** Son 5 uyarı
- **AJAX otomatik yenileme:** Her 15 saniyede sayfa yenilenmeden güncellenir

### Cihaz Detay Sayfası

macOS Etkinlik Monitörü'ne benzer sekmeli yapı:

| Sekme | İçerik |
|---|---|
| Genel | Anlık CPU%, RAM%, Disk% göstergeleri + donanım bilgileri |
| CPU | Sistem/Kullanıcı/Boş dağılımı, frekans, thread sayısı + zaman serisi grafik |
| Bellek | Kullanılan/Kullanılabilir/Önbellek dağılımı + swap bilgisi |
| Disk | Okuma/yazma hızı grafikleri |
| Ağ | Gönderilen/alınan veri grafikleri |

Tüm grafikler Chart.js ile çizilir ve `/devices/<mac>/stats/` API'sinden kronolojik veri çeker.

### Diğer Sayfalar

- **Cihaz Listesi:** Tüm cihazlar tablo halinde, aktif/pasif durumları
- **Uyarı Listesi:** Tüm uyarılar, filtrelenebilir, çözüldü işaretlenebilir
- **Konum Formu:** Cihaza bina/kat/oda bilgisi atama
- **Manuel Uyarı:** Elle uyarı oluşturma

---

## 8. Güvenlik ve Hata Yönetimi

### Otomatik Uyarı Sistemi

Sunucu her heartbeat'te eşik kontrolü yapar:

```python
if cpu_percent >= 90:   → Alert(CPU_HIGH)
if ram_percent >= 90:   → Alert(RAM_HIGH)  
if disk_percent >= 90:  → Alert(DISK_FULL)
```

### Cihaz Durumu Takibi

Her sayfa yüklendiğinde `mark_stale_devices_inactive()` çalışır:  
Son 2 dakikada sinyal göndermeyen cihazlar otomatik "Pasif" olarak işaretlenir.

### Django Başlatma Güvenliği

`baslat.py`, port 8000'i aktif olarak dinleyene kadar agent başlatmaz. Böylece sunucu hazır değilken agent bağlantı hatası almaz.

### Ortam Değişkenleri

Tüm hassas bilgiler (SECRET_KEY, DB şifresi) `.env` dosyasında tutulur, kaynak koda gömülmez.

---

## 9. Karşılaşılan Teknik Zorluklar ve Çözümleri

| Zorluk | Çözüm |
|---|---|
| Django hazır olmadan agent başlıyordu | `baslat.py`'de port 8000'e TCP bağlantısı denenene kadar döngü |
| `python-dotenv` kurulu değildi | `requirements.txt`'e eklendi, pip ile kuruldu |
| Supabase SSL gerektiriyor | `settings.py`'de `sslmode` ortam değişkeninden okunacak şekilde düzenlendi |
| `cpu_percent()` ilk çağrıda 0.0 dönüyordu | `cpu_times_percent(interval=1)` ile ölçüm yapılıp `100 - idle` kullanıldı |
| Grafik verisi ters sıradaydı | `device_stats` endpoint'i veriyi `reversed()` ile kronolojik döndürecek şekilde düzeltildi |
| Veritabanı hızla doluyordu | Cihaz başına 1440 kayıt limiti + timestamp bazlı otomatik temizleme eklendi |
| Admin'de N+1 sorgu sorunu | `list_select_related = ('device',)` ile tek sorguda çözüldü |
| Tüm tablolarda index yoktu | 4 composite index eklendi ve migration ile uygulandı |

---

## 10. Proje İstatistikleri

| Metrik | Değer |
|---|---|
| Toplam Python dosyası | 8 |
| Toplam satır sayısı (yaklaşık) | ~1500 satır |
| Veritabanı modeli | 5 |
| API endpoint | 12 |
| UI sayfası | 6 |
| Migration dosyası | 6 |
| Heartbeat'teki ölçüm sayısı | 27 |
| Heartbeat aralığı | 15 saniye |
| Cihaz başına max veri saklama | 6 saat (1440 kayıt) |
| DB indeksi | 4 composite index |

---

## 11. Gelecek Geliştirme Fikirleri

- **E-posta / SMS bildirimi** — Uyarı oluşunca otomatik bildirim
- **Kullanıcı yönetimi** — Cihaz bazlı yetkilendirme
- **Tarihsel veri analizi** — Günlük/haftalık ortalama grafikler
- **WebSocket** — REST polling yerine anlık push güncelleme
- **Docker** — Kolay kurulum için konteynerleştirme
- **Dışarıdan erişim** — Ngrok / VPS ile internet üzerinden izleme
- **Mobil uygulama** — React Native ile telefon bildirimleri

---

## 12. Kurulum Özeti

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. .env dosyasını oluştur (Supabase bilgileriyle)

# 3. Veritabanı tablolarını ve index'leri oluştur
python manage.py migrate

# 4. Sistemi başlat (tek komut)
python baslat.py
# veya: CALISTIR.bat dosyasına çift tıkla
```

Tarayıcıdan `http://127.0.0.1:8000` adresine gidildiğinde dashboard otomatik açılır.

---

*DevMonitor — Hamza Hakverir & Yunus Emre Edizer — 2026*
