"""
Ham heartbeat geçmişinin dosya sistemi arşivi.

İlişkisel veritabanı sadece canlı özet tutar (bkz. Device.live_metrics);
geçmişe dönük ham loglar burada cihaz+gün bazında JSONL dosyalarına yazılır
ve sadece gerektiğinde (CSV export, geçmiş inceleme) okunur.

Not: MAC adresindeki ':' Windows'ta dosya/dizin adında geçersiz olduğu için
dizin adında '-' ile değiştirilir.
"""
import json
import re
from pathlib import Path

from django.conf import settings

_DAY_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _safe_mac(mac_address):
    # ':' okunabilirlik için '-' yapılır; geri kalan her şey (özellikle '.', '/', '\\')
    # path traversal'ı önlemek için '_' ile değiştirilir — mac_address register_device
    # endpoint'inden serbest metin olarak geldiği için burada güvenli olmak gerekir.
    return re.sub(r'[^A-Za-z0-9-]', '_', mac_address.replace(':', '-'))


def _archive_dir():
    return Path(getattr(settings, 'ARCHIVE_DIR', Path(settings.BASE_DIR) / 'archive'))


def _device_dir(mac_address):
    return _archive_dir() / _safe_mac(mac_address)


def append_heartbeat(mac_address, payload, when):
    """Bir heartbeat'i <archive>/<mac>/<YYYY-MM-DD>.jsonl dosyasına ekler (append)."""
    device_dir = _device_dir(mac_address)
    device_dir.mkdir(parents=True, exist_ok=True)
    file_path = device_dir / f"{when:%Y-%m-%d}.jsonl"
    record = dict(payload)
    record['timestamp'] = when.isoformat()
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')


def read_recent(mac_address, limit=100):
    """En güncel günden geriye dolaşarak `limit` kadar kaydı kronolojik sırada (eski->yeni) döndürür."""
    device_dir = _device_dir(mac_address)
    if not device_dir.exists():
        return []

    records = []
    for file_path in sorted(device_dir.glob('*.jsonl'), reverse=True):
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break

    records.reverse()
    return records


def list_days(mac_address):
    """Cihaza ait arşivlenmiş günleri (tarih + dosya boyutu), eskiden yeniye sıralı döndürür."""
    device_dir = _device_dir(mac_address)
    if not device_dir.exists():
        return []
    return [
        {'date': file_path.stem, 'size_bytes': file_path.stat().st_size}
        for file_path in sorted(device_dir.glob('*.jsonl'))
    ]


def day_file_path(mac_address, day):
    """Belirli bir günün (YYYY-MM-DD) ham arşiv dosya yolunu döndürür; geçersiz/yoksa None.
    `day` sıkı bir biçimde doğrulanır — kullanıcıdan gelen bir URL parçası olduğu için
    path traversal'a karşı tam eşleşme (fullmatch) şart.
    """
    if not _DAY_RE.fullmatch(day):
        return None
    file_path = _device_dir(mac_address) / f"{day}.jsonl"
    return file_path if file_path.exists() else None
