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

## 5. Veritabanı Tasarımı (7 Tablo + 1 JSONB Özet Hücresi)

```
Device (Cihaz) — MAC adresi birincil anahtar
  │   └── live_metrics (JSONB)  → CANLI ÖZET: son 10 ölçüm + 24 saatlik kayan ortalama
  │                                 (bkz. Bölüm 8 — Mimari Kararlar)
  │
  ├── HardwareSpec [1'e 1]   → İşlemci, RAM, ekran kartı, IP, bilgisayar adı
  ├── Location [1'e 1]       → Bina, Kat, Oda
  ├── DeviceThreshold [1'e 1]→ Cihaza özel uyarı eşikleri
  ├── Tag [Çoka çok]         → Renkli etiketler
  │
  ├── Alert [1'e çok]        → Oluşan sistem uyarıları
  └── DeviceStatusLog [1'e çok] → Online/Offline geçiş kayıtları
```

> **Not:** Önceki sürümde her heartbeat ayrı bir satır olarak `HeartbeatLog`
> tablosuna ekleniyor, saatlik özetler de ayrı bir `HourlyAggregate` tablosunda
> tutuluyordu. Hocamızın geri bildirimi üzerine bu iki tablo tamamen kaldırıldı —
> bkz. Bölüm 8.

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

### Hocanın Geri Bildirimi: "İlişkisel Veritabanı Şişmesi" Sorunu

İlk sürümde her heartbeat (15 saniyede bir) `HeartbeatLog` tablosuna **yeni bir
satır** olarak ekleniyordu. Hocamız bunun binlerce cihazlı bir ortamda
veritabanını kısa sürede kilitleyeceğini belirtti ve mimariyi iki parçaya
ayırmamızı istedi: **canlı özet** (ilişkisel DB) + **ham arşiv** (ilişkisel
olmayan depolama). Aşağıdaki bölümler bu geri bildirim üzerine yapılan
değişiklikleri açıklar.

### Yeni Veri Saklama Stratejisi: Özet Tablo + JSONB

`HeartbeatLog` ve `HourlyAggregate` tabloları kaldırıldı. Artık her cihaz,
`Device` tablosunda **tek bir satırla** temsil ediliyor; bu satırın
`live_metrics` sütunu PostgreSQL'in **JSONB** tipinde tutuluyor:

```json
{
  "recent": [ {"...tam heartbeat verisi...", "timestamp": "..."} ],   // en fazla 10
  "windows": {
    "cpu_percent":  {"sum": 812.4, "count": 34, "buckets": [{"hour": "...", "sum": 41.2, "count": 4, "max": 55.0}, ...]},
    "ram_percent":  { "...": "..." },
    "disk_percent": { "...": "..." }
  }
}
```

Yeni bir heartbeat geldiğinde **satır eklenmez (INSERT yok)** — `recent`
listesinin en eski elemanı silinip dizi bir yana kaydırılır (shift), yeni veri
sona eklenir; hücre **UPDATE** edilir.

### Geçmiş Verinin Arşivlenmesi (Dosya Sistemi)

Geçmişe dönük ham loglar artık ilişkisel veritabanında değil, dosya sisteminde
tutuluyor: `archive/<mac-adresi>/<YYYY-MM-DD>.jsonl`. Her satır bir heartbeat'i
temsil eden bir JSON nesnesidir. Bu dosyalar sadece CSV dışa aktarımda veya
geçmiş inceleme yapılırken okunur — canlı dashboard hiçbir zaman bu dosyalara
dokunmaz. (Alternatif olarak MongoDB gibi ilişkisel olmayan bir veritabanı da
kullanılabilirdi; bu projede kurulum basitliği için dosya sistemi seçildi.)

### 24 Saatlik Ortalama Matematiği: Kayan Pencere (Sliding Window)

Hocamızın bıraktığı görev, "24 saatlik süre dolup yeni güne geçildiğinde veya
hareketli ortalamadan eski veriler çıkarılırken bu matematiğin nasıl
çalışacağı" idi. Çözümümüz **saat granülerlikli sabit-boyutlu bir döngüsel
arabellek (circular buffer)** kullanmak:

```
Her metrik (CPU/RAM/Disk) için saatlik "bucket"lar tutulur: {saat, sum, count, max}

Yeni değer v geldiğinde (O(1)):
    bucket.sum   += v ;  bucket.count   += 1     (v'nin ait olduğu saate)
    window.sum   += v ;  window.count   += 1     (24 saatlik toplam)

Bir bucket 24 saatlik pencereden çıkarken (yeni saate geçişte):
    window.sum   -= evicted.sum
    window.count -= evicted.count

Ortalama = window.sum / window.count   (her zaman — DB'deki tüm satırları
                                         yeniden toplamadan)
```

Bu yaklaşımın **takvim günü sıfırlaması yoktur** — pencere her zaman "şu anki
zamandan 24 saat öncesine kadar" kayar. Bu sayede gece yarısı sınırında
ortalama aniden sıfırlanıp zıplamaz; istatistikte buna **sliding window
aggregation** (kayan pencere toplulaştırması) denir ve okulda gördüğümüz
hareketli ortalama (moving average) konusunun, sabit bellek kullanan/O(1)
güncellenen bir versiyonudur. Matematiğin doğruluğu `monitoring/tests.py`
içindeki testlerle (200 saatlik simülasyon dahil, toplam sum/count'ın hiçbir
zaman bucket içeriğinden sapmadığını doğrulayan testler) kanıtlanmıştır.

### Önbellek (Cache)

Dashboard özet verileri (toplam cihaz, aktif cihaz, uyarı sayısı) 30 saniye boyunca bellekte tutulur. Her kullanıcı sayfayı yenilediğinde veritabanına sorgu atmak yerine önbellekten hızlıca döndürülür.

### Agent Çökme Koruması ve Yetki Kısıtlaması (Client Guard)

Hocamızın bir diğer talebi, `agent.py`'nin çökmesine karşı işletim sistemi
seviyesinde koruma ve amatör kullanıcıların onu Görev Yöneticisi'nden
kapatmasını engelleyecek yetki sınırlandırmasıydı. `install_service.py`,
agent.py'yi bir **Windows Servisi** olarak çalıştırarak bunu iki katmanda
sağlıyor:

1. **Süreç seviyesi:** Servis içindeki Python döngüsü, agent.py alt süreci
   çökerse 5 saniye içinde otomatik yeniden başlatır.
2. **Servis seviyesi (`python install_service.py secure`):**
   - `sc failure` komutu ile Windows Servis Kontrol Yöneticisi'ne (SCM), servisin
     kendisi (host süreç) çökse bile otomatik yeniden başlatma talimatı verilir
     — Python döngüsünün üstüne eklenen ikinci bir koruma katmanı.
   - `sc sdset` komutu ile servisin güvenlik tanımlayıcısı (ACL) değiştirilir:
     Start/Stop/Delete yetkisi sadece **Administrators** ve **SYSTEM**'e
     açıktır. Standart/amatör bir kullanıcı Görev Yöneticisi, `services.msc`
     veya `sc stop` ile servisi durduramaz ("Access is denied" hatası alır).

**Linux tarafı (`devmonitor.service`):** `Restart=always` (her türlü beklenmedik
çıkışta yeniden başlatma), `OOMScoreAdjust=-1000` (bellek darlığında OOM killer
bu süreci hedef almaz), `ProtectSystem=strict`/`ProtectHome=read-only`/
`NoNewPrivileges=true` (hafif sandbox — agent.py disk'e yazmadığı için güvenli).
Ekibimizin ilk taslağında önerilen `KillMode=none` **kasıtlı olarak
kullanılmadı** — bu ayar modern systemd'de orphan (sahipsiz) süreçler
bırakabildiği için resmi olarak önerilmiyor. "Amatör kullanıcı durduramasın"
gereksinimi Linux'ta ek bir ayar gerektirmeden zaten sağlanıyor: bu bir sistem
geneli (system-wide) unit olduğu için `systemctl stop devmonitor` zaten
root/sudo veya polkit yetkisi ister.

### Hedef Bilgisayara Kurulum: `setup_agent.py`

İzlenecek bir bilgisayara agent'ı kurmak için tek bir script yeterli:

```bash
python setup_agent.py
```

Script agent'ın bağımlılıklarını (`psutil`, `requests` — Django/DRF gibi sunucu
bağımlılıkları DEĞİL) kurar, sunucu adresini sorar ve platforma göre otomatik
olarak Windows Servisi (`install_service.py install` + `secure` + `start`) veya
Linux systemd unit'ini (root yetkisiyle `/etc/systemd/system/devmonitor.service`)
kurup başlatır. PyInstaller ile `.exe` paketleme değerlendirildi ancak bu
oturumda uygulanmadı — `setup_agent.py` script'i kurulum gereksinimini zaten
karşıladığı ve PyInstaller'ın her platformda gerçek bir makinede inşa edilip
test edilmesi gerektiği için şimdilik kapsam dışı bırakıldı.

### Ham Veri Arşivine Erişim API'si

Sadece CSV export değil, dosya sistemi arşivindeki ham günlük dosyalarına da
API üzerinden erişilebiliyor:

| Method | URL | Açıklama |
|---|---|---|
| GET | `ui/devices/<mac>/archive/` | Cihaza ait arşivlenmiş günleri (tarih + dosya boyutu) listeler |
| GET | `ui/devices/<mac>/archive/<YYYY-MM-DD>/download/` | Belirli bir günün ham `.jsonl` dosyasını indirir |

Bu endpoint'leri eklerken `archive.py`'de gerçek bir **path traversal**
güvenlik açığı bulundu ve düzeltildi: `mac_address`, `register_device`
endpoint'inden serbest metin olarak geldiği için (`"../../etc"` gibi) kötü
niyetli bir değer dosya sistemi yolunu kaçırabilirdi. Düzeltme: dizin adı
üretirken alfanümerik ve `-` dışındaki her karakter `_` ile değiştiriliyor;
`day` parametresi de sıkı bir tarih regex'iyle (`fullmatch`) doğrulanıyor.

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
| Veritabanı satır satır insert ile şişiyordu (hoca geri bildirimi) | `HeartbeatLog`/`HourlyAggregate` tabloları kaldırıldı; `Device.live_metrics` (JSONB) ile tek-satır özet + dosya sistemi arşivine geçildi (bkz. Bölüm 8) |
| Postgres'te `SELECT ... FOR UPDATE`, nullable OneToOne (`threshold`) JOIN'inde hata veriyordu | `select_for_update(of=('self',))` ile kilit sadece `Device` tablosuna uygulandı |
| Admin panelinde 4 model görünmüyordu | `Tag`, `DeviceThreshold`, `DeviceStatusLog` admin.py'e eklendi |
| `install_service.py`'deki `_sc()` Türkçe Windows konsolunda `sc.exe` çıktısını decode ederken çöküyordu (`secure` komutunu da kırıyordu) | `subprocess.run(..., errors='replace')` + yazdırma sırasında ASCII fallback eklendi |
| Arşiv listeleme/indirme API'si eklenirken `mac_address`'in serbest metin olması path traversal riski oluşturuyordu | `archive._safe_mac` alfanümerik+`-` dışındaki her karakteri `_`'ye çeviriyor; `day` parametresi sıkı regex `fullmatch` ile doğrulanıyor |

---

## 11. Proje İstatistikleri

| Metrik | Değer |
|---|---|
| Veritabanı tablosu (model) | 7 (+ `Device.live_metrics` JSONB özet hücresi) |
| API uç noktası (endpoint) | 20 |
| Web arayüzü sayfası | 9 |
| Heartbeat'teki ölçüm sayısı | 40+ alan |
| Heartbeat aralığı | 15 saniye |
| Canlı özette tutulan son ölçüm sayısı | 10 (cihaz başına, `live_metrics.recent`) |
| Kayan ortalama penceresi | 24 saat (saatlik bucket, O(1) güncelleme) |
| Ham geçmiş depolama | Dosya sistemi (`archive/<mac>/<tarih>.jsonl`) — sınırsız, sadece gerektiğinde okunur |
| Veritabanı bileşik indeks sayısı | 4 |
| Mimari değişikliğe ait birim test sayısı | 19 (`monitoring/tests.py`) |

---

## 12. Çalıştırma

```bash
# Tek komutla başlat (Mac/Linux)
python baslat.py

# Windows
CALISTIR.bat dosyasına çift tıkla

# Windows Servisi olarak (çökme koruması + yetki kısıtlaması ile, bkz. Bölüm 8)
python install_service.py install
python install_service.py secure
python install_service.py start

# İzlenecek hedef bilgisayara kurulum (Windows/Linux otomatik, bkz. Bölüm 8)
python setup_agent.py
```

| Sayfa | Adres |
|---|---|
| Ana Panel | http://127.0.0.1:8000/ |
| Cihazlar | http://127.0.0.1:8000/api/monitoring/ui/devices/ |
| Uyarılar | http://127.0.0.1:8000/api/monitoring/ui/alerts/ |
| Yönetim Paneli | http://127.0.0.1:8000/admin/ |

---

*DevMonitor — Hamza Hakverir & Yunus Emre Edizer — 2026*
