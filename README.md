# Donanim Izleme Sistemi (Hardware Monitoring System)

Django ve Django REST Framework ile gelistirilmis, ag uzerindeki bilgisayarlarin donanim bilgilerini merkezi olarak izleyen bir web uygulamasi.

---

## Proje Yapisi

```
hardware_monitoring_system/
├── core/                        # Django proje ayarlari
│   ├── settings.py              # Veritabani, uygulama ayarlari
│   ├── urls.py                  # Ana URL yonlendirme
│   ├── wsgi.py
│   └── asgi.py
├── monitoring/                  # Ana uygulama
│   ├── models.py                # Veritabani modelleri (5 model)
│   ├── views.py                 # API ve UI view'lari
│   ├── urls.py                  # URL tanimlari (10 API + 4 UI endpoint)
│   ├── serializers.py           # DRF serializer'lari
│   ├── admin.py                 # Django admin kayitlari
│   ├── migrations/              # Veritabani migration dosyalari
│   └── templates/monitoring/    # HTML sablonlari
│       ├── base.html            # Ana sablon (navbar, Bootstrap)
│       ├── device_list.html     # Cihaz listesi sayfasi
│       ├── alert_list.html      # Uyari listesi sayfasi
│       ├── add_location.html    # Konum ekleme formu
│       └── add_alert.html       # Uyari ekleme formu
├── agent.py                     # Istemci ajan (psutil ile veri toplar)
└── manage.py
```

---

## Teknoloji Yigini

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, Django 5.x |
| REST API | Django REST Framework |
| Veritabani | PostgreSQL (Supabase) |
| Arayuz | Django Templates + Bootstrap 5 |
| Istemci Ajan | Python (psutil, requests) |

---

## Veritabani Modelleri

### `Device` — Kayitli bilgisayarlar
| Alan | Tip | Aciklama |
|---|---|---|
| `mac_address` | CharField (PK) | Benzersiz kimlik |
| `os_info` | CharField | Isletim sistemi bilgisi |
| `is_active` | BooleanField | Aktif/pasif durumu |
| `created_at` | DateTimeField | Kayit tarihi |

### `Location` — Cihaz konumlari
| Alan | Tip | Aciklama |
|---|---|---|
| `device` | OneToOneField → Device | Bagli cihaz |
| `building` | CharField | Bina adi |
| `floor` | CharField | Kat |
| `room` | CharField | Oda numarasi |

### `HardwareSpec` — Donanim ozellikleri
| Alan | Tip | Aciklama |
|---|---|---|
| `device` | OneToOneField → Device | Bagli cihaz |
| `cpu_info` | CharField | Islemci bilgisi |
| `ram_total` | CharField | Toplam RAM (GB) |
| `vga_info` | CharField | Ekran karti bilgisi |
| `last_updated` | DateTimeField | Son guncelleme |

### `HeartbeatLog` — Canlilik kayitlari
| Alan | Tip | Aciklama |
|---|---|---|
| `device` | ForeignKey → Device | Bagli cihaz |
| `timestamp` | DateTimeField | Sinyal zamani |

### `Alert` — Uyarilar
| Alan | Tip | Aciklama |
|---|---|---|
| `device` | ForeignKey → Device | Bagli cihaz |
| `alert_type` | CharField | Uyari turu (CPU_HIGH, DISK_FULL vb.) |
| `message` | TextField | Uyari detayi |
| `is_resolved` | BooleanField | Cozuldu mu? |
| `created_at` | DateTimeField | Olusturulma tarihi |

---

## API Endpoint'leri

Base URL: `http://127.0.0.1:8000/api/monitoring/`

| # | Method | URL | Aciklama |
|---|---|---|---|
| 1 | GET | `devices/` | Tum cihazlari listele |
| 2 | POST | `devices/register/` | Yeni cihaz kaydet |
| 3 | GET | `devices/<mac>/` | Tek cihaz detayi |
| 4 | POST | `heartbeats/` | Canlilik sinyali al |
| 5 | GET | `locations/` | Tum konumlari listele |
| 6 | POST | `locations/add/` | Konum ekle |
| 7 | POST | `hardware/` | Donanim bilgisi guncelle/ekle |
| 8 | GET | `hardware/<mac>/` | Cihaz donanim bilgisini getir |
| 9 | GET | `alerts/` | Tum uyarilari listele |
| 10 | POST/PATCH | `alerts/<id>/resolve/` | Uyariyi cozuldu isaretle |

---

## Arayuz (UI) Sayfalari

| URL | Aciklama |
|---|---|
| `/api/monitoring/ui/devices/` | Kayitli cihazlar listesi |
| `/api/monitoring/ui/alerts/` | Uyarilar listesi |
| `/api/monitoring/ui/add-location/` | Cihaza konum atama formu |
| `/api/monitoring/ui/add-alert/` | Manuel uyari olusturma formu |

---

## Kurulum ve Calistirma

### 1. Gereksinimleri Kur

```bash
pip install django djangorestframework psycopg2-binary psutil requests
```

### 2. Veritabani Ayarlarini Yapin

`core/settings.py` dosyasindaki `DATABASES` bolumunu kendi PostgreSQL bilgilerinizle guncelleyin:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'veritabani_adi',
        'USER': 'kullanici_adi',
        'PASSWORD': 'sifreniz',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

> Supabase kullaniyorsaniz `OPTIONS: {'sslmode': 'require'}` ekleyin.

### 3. Tablolari Olustur

```bash
python manage.py migrate
```

### 4. Sunucuyu Baslat

```bash
python manage.py runserver
```

Tarayicidan `http://127.0.0.1:8000/api/monitoring/ui/devices/` adresine gidin.

---

## Ajan Uygulamasi (agent.py)

`agent.py`, izlenecek bilgisayarlarda calistirilacak istemci betigidir. Calistirildigi bilgisayarin MAC adresi, isletim sistemi ve donanim bilgilerini otomatik olarak sunucuya kaydeder.

```bash
python agent.py
```

**Toplanan veriler:**
- MAC adresi (`uuid` modulu ile)
- Isletim sistemi (`platform` modulu ile)
- Islemci bilgisi (`platform.processor()`)
- Toplam RAM (`psutil.virtual_memory()`)

**Akis:**
1. Bilgisayarin MAC adresini tespit eder
2. `POST /api/monitoring/devices/register/` endpoint'ine kayit istegi gonderir
3. Cihaz zaten kayitliysa bilgi mesaji verir

---

## Gelistirici Notlari

- `DEBUG = True` sadece gelistirme ortami icindir, production'da `False` yapilmali
- `SECRET_KEY` production'da degistirilmeli ve ortam degiskeninden okunmali
- `ALLOWED_HOSTS` production'da sunucu IP/domain adresiyle guncellenmeli
