# DevMonitor — Donanım İzleme Sistemi
## Proje Sunum Raporu

**Geliştirici:** Hamza Hakverir & Yunus Emre Edizer
**Tarih:** Mayıs 2026
**Platform:** Web Tabanlı (Python / Django)

---

## 1. Projenin Amacı

DevMonitor, bir ağdaki bilgisayarların donanım ve anlık performans bilgilerini **tek bir web ekranından** gerçek zamanlı izlemek için geliştirilmiş bir sistem izleme uygulamasıdır.

**Çözülen problem:** Laboratuvar veya ofis ortamında her bilgisayarın başına geçmeden, tüm cihazların CPU, RAM, disk, ağ ve batarya durumunu merkezi olarak görmek.

---

## 2. Sistem Nasıl Çalışır? (Genel Mimari)

Sistem üç ana parçadan oluşur:

```
┌─────────────────────────────────────────────────────┐
│             İzlenen Bilgisayarlar                   │
│   agent.py       agent.py        agent.py           │
│   (Cihaz 1)      (Cihaz 2)       (Cihaz N)          │
└──────────┬───────────┬──────────────┬───────────────┘
           │ HTTP POST  │ her 15 sn    │
           ▼            ▼              ▼
┌─────────────────────────────────────────────────────┐
│          Django Web Sunucusu (REST API)              │
│   /devices/register/   /heartbeats/   /alerts/       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│       PostgreSQL Veritabanı (Supabase bulut)         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Web Arayüzü (Tarayıcı)                  │
│  Dashboard | Cihaz Listesi | Cihaz Detayı | Uyarılar │
└─────────────────────────────────────────────────────┘
```

**Kısaca:** İzlenen her bilgisayarda küçük bir Python betiği (`agent.py`) çalışır. Bu betik bilgisayarın anlık verilerini toplayıp 15 saniyede bir merkezi sunucuya gönderir. Sunucu verileri veritabanına kaydeder ve web arayüzünden erişilebilir hale getirir.

---

## 3. Kullanılan Teknolojiler

| Katman | Teknoloji | Açıklama |
|---|---|---|
| Sunucu Dili | Python 3.12 | Ana programlama dili |
| Web Çatısı (Framework) | Django 5.1.4 | Sunucu tarafı web geliştirme |
| Uygulama Programlama Arayüzü (API) | Django REST Framework 3.17 | Ajan ile sunucu arasındaki veri köprüsü |
| Veritabanı | PostgreSQL (Supabase) | Bulut üzerinde kalıcı veri saklama |
| Önbellek (Cache) | Django LocMemCache | Sık sorgulanan verileri bellekte tutar |
| Arayüz | Bootstrap 5 + Chart.js 4 | Görsel tasarım + grafikler |
| Ajan Kütüphanesi | psutil 6.0 | Bilgisayarın donanım verilerini okur |
| HTTP İstemcisi | requests 2.32 | Ajanın sunucuya veri göndermesi |

---

## 4. Verileri Bilgisayardan Nasıl Alıyoruz?

### `agent.py` ve `psutil` Kütüphanesi

`psutil` (process and system utilities — işlem ve sistem yardımcı araçları), işletim sisteminin çekirdeğine (kernel) sorarak donanım verilerini okuyan bir Python kütüphanesidir. Windows, macOS ve Linux'ta aynı kod çalışır.

#### Başlangıçta (Agent ilk açıldığında, bir kez):

| Ne Yapılır | Nasıl Yapılır |
|---|---|
| MAC adresi (ağ kartı kimliği) okunur | `uuid.getnode()` → işletim sisteminden |
| IP adresi ve bilgisayar adı alınır | `socket.gethostname()`, `socket.gethostbyname()` |
| İşlemci (CPU) modeli okunur | Windows: `wmic cpu` komutu · macOS: `sysctl -n machdep.cpu.brand_string` · Linux: `/proc/cpuinfo` |
| Ekran kartı (GPU) okunur | Windows: `wmic path win32_VideoController` · macOS: `system_profiler SPDisplaysDataType` · Linux: `lspci` |
| İşletim sistemi bilgisi alınır | `platform.system()` + `platform.version()` |
| Sunucuya kayıt olunur | `POST /devices/register/` → sunucu bir kimlik token'ı (şifre anahtarı) döner |

#### Her 15 Saniyede (Sürekli Döngü):

```
psutil kütüphanesi çağrılır
    │
    ├─ cpu_times_percent(interval=1)
    │     → 1 saniye boyunca CPU'yu ölçer
    │     → sistem görevleri / kullanıcı uygulamaları / boşta yüzde olarak ayrılır
    │
    ├─ cpu_freq()          → İşlemci frekansı (MHz/GHz)
    ├─ cpu_percent(percpu) → Her çekirdek ayrı ayrı ölçülür
    ├─ sensors_temperatures() → CPU ısısı (destekleniyorsa)
    │
    ├─ virtual_memory()    → RAM: toplam, kullanılan, boş, önbellek
    ├─ swap_memory()       → Takas alanı kullanımı
    │
    ├─ disk_usage('/')     → Disk doluluk yüzdesi
    ├─ disk_io_counters()  → Toplam okunan/yazılan veri miktarı
    ├─ disk_partitions()   → Tüm disk bölümleri
    │
    ├─ net_io_counters()       → Toplam ağ trafiği
    ├─ net_io_counters(pernic) → Her ağ arayüzü ayrı ayrı
    │
    ├─ sensors_battery()   → Batarya yüzdesi + şarjda mı?
    │
    ├─ process_iter()      → Tüm çalışan programlar taranır
    │     → CPU kullanımına göre sıralanır → Top 10 alınır
    │
    └─ POST /heartbeats/   → Tümü JSON olarak sunucuya gönderilir
```

---

## 5. Veritabanı Tasarımı (9 Tablo)

```
Device (Cihaz) — MAC adresi birincil anahtar
  │
  ├── HardwareSpec [1'e 1]   → İşlemci, RAM, ekran kartı, IP, bilgisayar adı
  ├── Location [1'e 1]       → Bina, Kat, Oda
  ├── DeviceThreshold [1'e 1]→ Cihaza özel uyarı eşikleri
  ├── Tag [Çoka çok]         → Renkli etiketler
  │
  ├── HeartbeatLog [1'e çok] → Her 15 sn'deki anlık ölçümler
  ├── Alert [1'e çok]        → Oluşan sistem uyarıları
  ├── DeviceStatusLog [1'e çok] → Online/Offline geçiş kayıtları
  └── HourlyAggregate [1'e çok] → Saatlik ortalama/maksimum değerler
```

---

## 6. Cihaz Detay Sayfasındaki Verilerin Açıklaması

Bu bölüm, ekranda gördüğünüz ama tam olarak ne anlama geldiğini bilmediğiniz alanları açıklar.

---

### 6.1 CPU (İşlemci) Bölümü

| Ekrandaki İsim | Ne Anlama Gelir |
|---|---|
| **CPU %** | İşlemcinin şu an ne kadarının meşgul olduğu. %100 → işlemci tamamen dolu. |
| **Sistem** | İşletim sisteminin çekirdek (kernel) işlemleri için harcadığı CPU yüzdesi. Yüksekse genellikle sürücü veya donanım sorunu işareti. |
| **Kullanıcı** | Sizin açtığınız uygulamaların (tarayıcı, ofis vb.) harcadığı CPU yüzdesi. |
| **Boş** | Kullanılmayan CPU kapasitesi. %0 ise işlemci tamamen dolu demektir. |
| **Frekans (MHz)** | İşlemcinin o an çalıştığı hız. Modern işlemciler yük altında hızlanır (Turbo Boost), boştayken yavaşlar (güç tasarrufu). 1000 MHz = 1 GHz. |
| **İş Parçacığı (Thread)** | İşlemcinin aynı anda yürütebileceği görev sayısı. 8 çekirdekli bir işlemcide genellikle 16 thread olur. |
| **Çekirdek Başına Kullanım** | Her CPU çekirdeğinin ayrı ayrı yük durumu. Bir çekirdek %100 iken diğerleri boşsa, program çok çekirdekli işlemi kullanamıyor demektir. |
| **CPU Sıcaklığı** | İşlemcinin anlık ısısı (°C). 80°C üstü tehlikeli bölge, 90°C+ işlemci kendini yavaşlatmaya başlar (thermal throttling). |

---

### 6.2 Bellek (RAM) Bölümü

RAM (Rastgele Erişim Belleği), bilgisayarın o an açık olan programları geçici olarak tuttuğu hızlı bellektir. Kapatınca içerik silinir.

| Ekrandaki İsim | Ne Anlama Gelir |
|---|---|
| **Fiziksel Bellek** | Bilgisayara takılı toplam RAM miktarı (örn. 16 GB). |
| **Kullanılan** | Şu an programların aktif olarak kullandığı RAM. |
| **Kullanılabilir** | Yeni bir program açılırsa hemen kullanılabilecek boş alan. |
| **Önbellek (Cache)** | İşletim sisteminin disk erişimini hızlandırmak için ayırdığı RAM. Gerekirse anında boşaltılır, sorun değildir. |
| **Takas Toplam (Swap Total)** | Sabit diskin RAM gibi kullanılan alanı. RAM dolunca işletim sistemi bazı verileri diske taşır. Disk çok daha yavaş olduğundan swap kullanımı bilgisayarı yavaşlatır. |
| **Takas Kullanılan (Swap Used)** | Şu an diske taşınmış olan veri miktarı. Bu değer yüksekse RAM yetersiz demektir — daha fazla RAM gerekebilir. |

---

### 6.3 Disk Bölümü

| Ekrandaki İsim | Ne Anlama Gelir |
|---|---|
| **Disk Kullanımı %** | Sabit diskin ne kadar dolu olduğu. %90 üstü kritik. |
| **Toplam Okunan (Disk Read)** | Sistem açılışından bu yana diskten okunmuş toplam veri. Bu bir hız değil, kümülatif (birikimli) toplamıdır. |
| **Toplam Yazılan (Disk Write)** | Sistem açılışından bu yana diske yazılmış toplam veri. |
| **Disk Giriş/Çıkış Grafiği** | Her 15 saniyedeki **değişimi** gösterir. Grafikte tepe varsa o an yoğun disk işlemi olmuş demektir (büyük dosya kopyalama, güncelleme vb.). |
| **Disk Bölümleri (Partitions)** | Diskin mantıksal olarak ayrıldığı bölümler. Windows'ta C:, D: gibi; macOS/Linux'ta `/`, `/home` gibi. Her bölümün doluluk oranı ayrı gösterilir. |
| **Bağlama Noktası (Mountpoint)** | Disk bölümünün dosya sisteminde hangi klasöre bağlandığı. macOS'ta `/` kök dizini, Windows'ta `C:\` gibi. |
| **Dosya Sistemi (Filesystem)** | Diskin verisi nasıl organize ettiği. APFS (macOS), NTFS (Windows), ext4 (Linux) gibi. |

---

### 6.4 Ağ Bölümü

| Ekrandaki İsim | Ne Anlama Gelir |
|---|---|
| **Alınan Veri (Bytes Recv)** | Sistem açılışından bu yana internetten/ağdan indirilen toplam veri. |
| **Gönderilen Veri (Bytes Sent)** | Sistem açılışından bu yana internete/ağa yüklenen toplam veri. |
| **Gelen Paket (Packets Recv)** | Ağdan alınan paket (veri paketi) sayısı. Veri küçük parçalara bölünerek iletilir, bunlara paket denir. |
| **Giden Paket (Packets Sent)** | Ağa gönderilen paket sayısı. |
| **Ağ Giriş/Çıkış Grafiği** | Her 15 saniyedeki ağ trafiği değişimi. Tepe anlar yoğun indirme/yükleme anlarını gösterir. |
| **Arayüz Bazında İstatistikler (Per-NIC Stats)** | NIC = Network Interface Card (Ağ Arayüzü Kartı). Bilgisayardaki her ağ bağlantısının trafiği ayrı ayrı gösterilir. Örneğin: `en0` (WiFi), `eth0` (kablo), `lo` (yerel döngü — internet dışı iç iletişim). Bir bilgisayarda birden fazla ağ bağlantısı olabilir; bu bölüm hangisinin ne kadar trafik yaptığını gösterir. |

---

### 6.5 Online/Offline Zaman Çizelgesi

Son 7 günü günlük satırlar halinde gösterir. Her satır bir günü temsil eder ve 24 saate bölünmüştür.

- **Yeşil bölge:** Cihaz o saatlerde açık ve veri gönderiyordu.
- **Kırmızı bölge:** Cihaz kapalıydı ya da agent çalışmıyordu.
- **Gri bölge:** Bilinmiyor (cihaz henüz sisteme kayıtlı değildi).

Bir çubuğun üstüne gelince tam saat aralığı gösterilir (örn. "14:30–16:00 Online").

---

### 6.6 24 Saatlik Trend Grafiği

Saatlik ortalama CPU ve RAM değerlerini gösterir. Anlık 15 saniyelik ölçümlerin aksine bu grafik saatlik özetler kullanır — "sabah 9-10 arası CPU genellikle ne kadardı?" sorusunu yanıtlar.

- **CPU Ort (Mavi çubuk):** O saatteki ortalama işlemci yükü.
- **CPU Max (Kırmızı kesikli çizgi):** O saatteki en yüksek işlemci yükü.
- **RAM Ort (Mavi çizgi):** O saatteki ortalama bellek kullanımı.

---

### 6.7 En Çok Kaynak Kullanan İşlemler (Top 10)

Bilgisayarda çalışan tüm programlar taranır, CPU kullanımına göre sıralanır ve en üstteki 10 tanesi listelenir.

| Sütun | Açıklama |
|---|---|
| **İşlem Adı** | Programın sistem adı (örn. `chrome`, `python`, `Finder`) |
| **CPU %** | O an işlemcinin ne kadarını kullandığı |
| **Bellek (MB)** | Programın RAM'de kapladığı alan (Megabayt) |
| **İş Parçacığı** | Programın aynı anda yürüttüğü görev sayısı |

---

## 7. Güvenlik Sistemi

### Token Tabanlı Kimlik Doğrulama

Her cihaz sisteme ilk kez kaydolduğunda sunucu 64 karakterlik rastgele bir **token** (şifre anahtarı) üretir. Bundan sonra agent her veri gönderiminde bu token'ı birlikte iletmek zorundadır. Token'sız veya yanlış token ile gelen istekler reddedilir.

```
Agent → POST /heartbeats/ + "Authorization: Token abc123..."
Sunucu → Token doğruysa veriyi kabul et, değilse 401 Yetkisiz hatası döndür
```

### Otomatik Uyarı Sistemi

Sunucu her heartbeat'te (her 15 saniyede bir) eşik kontrolü yapar:

| Uyarı Türü | Varsayılan Eşik | Önem Derecesi |
|---|---|---|
| CPU_HIGH | %80 uyarı / %90 kritik | WARNING / CRITICAL |
| RAM_HIGH | %80 uyarı / %90 kritik | WARNING / CRITICAL |
| DISK_FULL | %80 uyarı / %90 kritik | WARNING / CRITICAL |
| ANOMALY | Anlık değer ortalamanın 2 katı | WARNING |

Her cihaz için bu eşikler ayrıca özelleştirilebilir (DeviceThreshold modeli).

### Anomali Tespiti

Her 4 heartbeat'te bir sistem son 20 ölçümün ortalamasını hesaplar. Eğer anlık değer bu ortalamanın 2 katından fazlaysa "ani artış uyarısı" oluşturulur. Örnek: CPU genellikle %20 civarındayken aniden %60'a çıkması.

### Pasif Cihaz Tespiti

Sunucu her 30 saniyede bir kontrol eder: Son 2 dakikada hiç sinyal göndermeyen cihazlar otomatik "Pasif" olarak işaretlenir ve bir **DeviceStatusLog** kaydı oluşturulur.

### E-posta Bildirimi

`.env` dosyasında SMTP (e-posta sunucusu) ayarları yapılandırıldığında, CRITICAL seviyeli uyarılarda sistemin yöneticisine otomatik e-posta gönderilir.

---

## 8. Mimari Kararlar ve Performans

### Neden Supabase (bulut PostgreSQL)?

Ekip çalışmasını kolaylaştırmak için. Her iki geliştiricinin de aynı veritabanına erişebilmesi, farklı bilgisayarlardan test yapılabilmesi.

### Veri Saklama Stratejisi

- **Anlık veri:** Cihaz başına maksimum 1440 kayıt tutulur (= 6 saatlik veri, her 15 saniyede bir kayıt).
- **Saatlik özet:** Her ~25 saatte bir arka planda çalışan bir görev (thread) eski kayıtları saatlik ortalamalara çevirir ve `HourlyAggregate` tablosuna yazar. Bu özetler 30 gün saklanır.
- **Amaç:** Veritabanının dolmaması ve uzun vadeli trend analizine olanak tanıması.

### Önbellek (Cache)

Dashboard özet verileri (toplam cihaz, aktif cihaz, uyarı sayısı) 30 saniye boyunca bellekte tutulur. Her kullanıcı sayfayı yenilediğinde veritabanına sorgu atmak yerine önbellekten hızlıca döndürülür.

### Arka Plan İşlemi (Thread)

Saatlik ortalama hesaplama işlemi bir arka plan iş parçacığında (thread) çalışır. Bu sayede kullanıcı arayüzü bu hesaplama sırasında yavaşlamaz.

---

## 9. Web Arayüzü

### Dashboard (Ana Sayfa)

- 4 özet kart: Toplam / Aktif / Pasif cihaz sayısı ve bekleyen uyarı sayısı
- Aktif-Pasif cihaz oranını gösteren halka grafik (doughnut chart)
- Son uyarı türlerinin dağılımını gösteren çubuk grafik
- Son 5 uyarının listesi
- Her 15 saniyede sayfa yenilenmeden otomatik güncellenir (AJAX)

### Cihaz Listesi

- Tüm kayıtlı cihazlar tablo halinde
- Aktif cihazlar yeşil, pasif cihazlar kırmızı gösterge ile ayrışır
- Tag (etiket) filtresi ile gruplama yapılabilir
- Sayfalama desteği

### Cihaz Detay Sayfası

Yapışık (sticky) bölüm menüsü ile 6 ana bölüme hızlı geçiş:

1. **Genel:** Anlık CPU/RAM/Disk göstergeleri + donanım ve konum bilgisi
2. **CPU:** Sistem/Kullanıcı/Boş dağılımı, frekans, çekirdek başına kullanım grafiği
3. **Bellek:** Kullanılan/Önbellek/Kullanılabilir halka grafiği + zaman serisi
4. **Disk:** Okuma/Yazma hız grafiği + bölüm tablosu
5. **Ağ:** İndirme/Yükleme grafiği + arayüz bazında istatistikler
6. **Zaman Çizelgesi:** 7 günlük online/offline görünümü + 24 saatlik trend

### Uyarı Listesi

- Tüm uyarılar tarih, tür ve önem derecesiyle listelenir
- "Çözüldü" butonu ile uyarılar kapatılabilir
- CSV olarak dışa aktarım

### Diğer Sayfalar

- **Eşik Ayarları:** Her cihaz için CPU/RAM/Disk uyarı eşiklerini özelleştirme
- **Etiket (Tag) Yönetimi:** Renkli etiket oluşturma ve cihaza atama
- **Konum Atama:** Bina/Kat/Oda bilgisi ekleme

---

## 10. Karşılaşılan Teknik Zorluklar

| Zorluk | Çözüm |
|---|---|
| Django hazır olmadan agent başlıyordu | `baslat.py` port 8000'e TCP bağlantısı denenene kadar bekliyor |
| `cpu_percent()` ilk çağrıda 0 dönüyordu | `cpu_times_percent(interval=1)` ile 1 saniyelik ölçüm; `100 - boş` formulü |
| Grafik verisi ters sıradaydı | `device_stats` endpoint'i veriyi kronolojik sırayla döndürecek şekilde düzeltildi |
| Online/Offline çizelgesi zıt renk gösteriyordu | Başlangıç durumu `went_online_at` referansıyla geriye doğru zincir hesaplamasıyla düzeltildi |
| Veritabanı hızla doluyordu | 1440 kayıt limiti + saatlik özetleme sistemi |
| Admin panelinde 4 model görünmüyordu | `Tag`, `DeviceThreshold`, `DeviceStatusLog`, `HourlyAggregate` admin.py'e eklendi |

---

## 11. Proje İstatistikleri

| Metrik | Değer |
|---|---|
| Veritabanı tablosu (model) | 9 |
| API uç noktası (endpoint) | 20 |
| Web arayüzü sayfası | 9 |
| Heartbeat'teki ölçüm sayısı | 40+ alan |
| Heartbeat aralığı | 15 saniye |
| Cihaz başına anlık veri saklama | 6 saat (1440 kayıt) |
| Saatlik özet saklama süresi | 30 gün |
| Veritabanı bileşik indeks sayısı | 6 |
| Toplam Python kodu (yaklaşık) | ~1800 satır |

---

## 12. Çalıştırma

```bash
# Tek komutla başlat (Mac/Linux)
python baslat.py

# Windows
CALISTIR.bat dosyasına çift tıkla
```

| Sayfa | Adres |
|---|---|
| Ana Panel | http://127.0.0.1:8000/ |
| Cihazlar | http://127.0.0.1:8000/api/monitoring/ui/devices/ |
| Uyarılar | http://127.0.0.1:8000/api/monitoring/ui/alerts/ |
| Yönetim Paneli | http://127.0.0.1:8000/admin/ |

---

*DevMonitor — Hamza Hakverir & Yunus Emre Edizer — 2026*
