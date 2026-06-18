"""
Canlı özet mimarisinin (Device.live_metrics + dosya sistemi arşivi) testleri.

Hocanın açık sorusuna cevap olan kayan-pencere matematiğini (bkz.
monitoring/live_stats.py) ve dosya arşivini (monitoring/archive.py) kapsar.
DB'ye dokunmadıkları için SimpleTestCase kullanılır.
"""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from . import archive, live_stats


def _payload(cpu=10.0, ram=20.0, disk=30.0):
    return {'cpu_percent': cpu, 'ram_percent': ram, 'disk_percent': disk}


class ApplyHeartbeatRecentListTests(SimpleTestCase):
    """recent listesinin shift (kaydırma) davranışı — INSERT yerine UPDATE."""

    def test_recent_list_caps_at_limit_and_keeps_newest_last(self):
        live_metrics = {}
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(live_stats.RECENT_LIMIT + 5):
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=float(i)), now + timedelta(seconds=15 * i)
            )

        recent = live_metrics['recent']
        self.assertEqual(len(recent), live_stats.RECENT_LIMIT)
        # En eski 5 değer (0..4) düşmüş olmalı; liste eski->yeni sıralı kalmalı.
        self.assertEqual(recent[0]['cpu_percent'], 5.0)
        self.assertEqual(recent[-1]['cpu_percent'], float(live_stats.RECENT_LIMIT + 4))

    def test_each_recent_entry_has_timestamp(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        live_metrics = live_stats.apply_heartbeat({}, _payload(), now)
        self.assertEqual(live_metrics['recent'][0]['timestamp'], now.isoformat())


class SlidingWindowMathTests(SimpleTestCase):
    """24 saatlik kayan ortalama: O(1) güncelleme + eski bucket'ların düşmesi."""

    def test_average_with_no_data_is_none(self):
        self.assertIsNone(live_stats.window_average({}, 'cpu_percent'))

    def test_sum_and_count_accumulate_within_same_hour(self):
        now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        live_metrics = {}
        for cpu in (10.0, 20.0, 30.0):
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=cpu), now + timedelta(minutes=5)
            )
        window = live_metrics['windows']['cpu_percent']
        self.assertEqual(window['count'], 3)
        self.assertAlmostEqual(window['sum'], 60.0)
        self.assertAlmostEqual(live_stats.window_average(live_metrics, 'cpu_percent'), 20.0)
        # Hepsi aynı saate düştüğü için tek bucket olmalı.
        self.assertEqual(len(window['buckets']), 1)
        self.assertEqual(window['buckets'][0]['count'], 3)

    def test_old_buckets_are_evicted_after_24_hours(self):
        """Pencereden çıkan saatin payı toplamdan düşülür — sıfırdan yeniden toplanmaz."""
        live_metrics = {}
        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        for h in range(48):  # 48 saat, saatte bir heartbeat
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=float(h)), base + timedelta(hours=h)
            )
        window = live_metrics['windows']['cpu_percent']
        # Pencere sınırsız büyümemeli (saat granülerliği nedeniyle 24-25 arası kalır).
        self.assertLessEqual(len(window['buckets']), 25)
        # En eski saatler (h=0 civarı) artık ortalamada YOK; en yeni değerler ağır basmalı.
        self.assertGreater(live_stats.window_average(live_metrics, 'cpu_percent'), 30.0)

    def test_running_totals_never_drift_from_bucket_contents(self):
        """window.sum/count her zaman mevcut bucket'ların toplamına eşit olmalı (sızıntı yok)."""
        live_metrics = {}
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for h in range(200):
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=float(h % 50)), base + timedelta(hours=h)
            )
            window = live_metrics['windows']['cpu_percent']
            bucket_sum = sum(b['sum'] for b in window['buckets'])
            bucket_count = sum(b['count'] for b in window['buckets'])
            self.assertAlmostEqual(bucket_sum, window['sum'], places=9)
            self.assertEqual(bucket_count, window['count'])

    def test_no_calendar_day_reset(self):
        """Gece yarısı sınırında ortalama aniden sıfırlanıp zıplamamalı (gerçek kayan pencere)."""
        live_metrics = {}
        base = datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)  # gece yarısından 2 saat önce
        for h in range(4):  # 22:00, 23:00, 00:00, 01:00 — gün sınırını geçer
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=50.0), base + timedelta(hours=h)
            )
        # Gün geçişine rağmen tüm değerler hâlâ pencerede — ortalama sabit kalmalı.
        self.assertAlmostEqual(live_stats.window_average(live_metrics, 'cpu_percent'), 50.0)


class HourlyTrendTests(SimpleTestCase):
    def test_hourly_trend_matches_bucket_count(self):
        live_metrics = {}
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for h in range(5):
            live_metrics = live_stats.apply_heartbeat(
                live_metrics, _payload(cpu=10.0 * h, ram=5.0, disk=1.0), base + timedelta(hours=h)
            )
        rows = live_stats.hourly_trend(live_metrics)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1]['cpu_avg'], 40.0)
        self.assertEqual(rows[-1]['sample_count'], 1)


class ArchiveFileSystemTests(SimpleTestCase):
    """Dosya sistemi arşivi: yazma + okuma round-trip ve Windows-güvenli dosya adları."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(ARCHIVE_DIR=Path(self._tmp.name))
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_mac_with_colon_produces_windows_safe_directory(self):
        device_dir = archive._device_dir('AA:BB:CC:DD:EE:FF')
        # Sadece MAC'ten türetilen dizin adı kontrol edilir (tam yol Windows'ta
        # sürücü harfi nedeniyle ':' içerebilir, örn. "C:\...").
        self.assertNotIn(':', device_dir.name)
        self.assertEqual(device_dir.name, 'AA-BB-CC-DD-EE-FF')

    def test_append_then_read_recent_round_trip(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(3):
            archive.append_heartbeat(mac, _payload(cpu=float(i)), now + timedelta(seconds=i))

        records = archive.read_recent(mac, limit=10)
        self.assertEqual(len(records), 3)
        # Kronolojik sırada (eski->yeni) dönmeli.
        self.assertEqual([r['cpu_percent'] for r in records], [0.0, 1.0, 2.0])

    def test_read_recent_limit_is_respected_across_multiple_days(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        day1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        for i in range(3):
            archive.append_heartbeat(mac, _payload(cpu=float(i)), day1 + timedelta(seconds=i))
        for i in range(3, 6):
            archive.append_heartbeat(mac, _payload(cpu=float(i)), day2 + timedelta(seconds=i))

        records = archive.read_recent(mac, limit=4)
        self.assertEqual(len(records), 4)
        # En yeni 4 kayıt: gün1'in son değeri (2.0) + gün2'nin tamamı (3,4,5), kronolojik sırada.
        self.assertEqual([r['cpu_percent'] for r in records], [2.0, 3.0, 4.0, 5.0])

    def test_unknown_device_returns_empty_list(self):
        self.assertEqual(archive.read_recent('00:00:00:00:00:00'), [])

    def test_archived_record_is_valid_json_line(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        archive.append_heartbeat(mac, _payload(), now)
        file_path = archive._device_dir(mac) / f"{now:%Y-%m-%d}.jsonl"
        line = file_path.read_text(encoding='utf-8').strip()
        record = json.loads(line)
        self.assertEqual(record['cpu_percent'], 10.0)
        self.assertEqual(record['timestamp'], now.isoformat())

    def test_safe_mac_neutralizes_path_traversal(self):
        """mac_address register_device'tan serbest metin olarak geldiği için
        '../' gibi path traversal denemeleri dizin adında zararsız hale gelmeli.
        """
        device_dir = archive._device_dir('../../etc/passwd')
        archive_root = archive._archive_dir()
        # Hesaplanan dizin her zaman arşiv kökünün DOĞRUDAN bir alt klasörü olmalı —
        # '..' veya '/' ile kökün dışına çıkılamamalı.
        self.assertEqual(device_dir.parent, archive_root)
        self.assertNotIn('..', device_dir.name)
        self.assertNotIn('/', device_dir.name)
        self.assertNotIn('\\', device_dir.name)

    def test_list_days_returns_sorted_dates_with_sizes(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        day2 = datetime(2026, 1, 3, tzinfo=timezone.utc)
        archive.append_heartbeat(mac, _payload(), day1)
        archive.append_heartbeat(mac, _payload(), day2)

        days = archive.list_days(mac)
        self.assertEqual([d['date'] for d in days], ['2026-01-01', '2026-01-03'])
        self.assertTrue(all(d['size_bytes'] > 0 for d in days))

    def test_list_days_for_unknown_device_is_empty(self):
        self.assertEqual(archive.list_days('00:00:00:00:00:00'), [])

    def test_day_file_path_returns_path_for_existing_day(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        archive.append_heartbeat(mac, _payload(), now)

        file_path = archive.day_file_path(mac, '2026-01-01')
        self.assertIsNotNone(file_path)
        self.assertTrue(file_path.exists())

    def test_day_file_path_returns_none_for_missing_day(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        archive.append_heartbeat(mac, _payload(), datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(archive.day_file_path(mac, '2099-12-31'))

    def test_day_file_path_rejects_non_date_input(self):
        """URL'den gelen 'day' parametresi path traversal için kullanılamamalı."""
        mac = 'AA:BB:CC:DD:EE:FF'
        archive.append_heartbeat(mac, _payload(), datetime(2026, 1, 1, tzinfo=timezone.utc))
        for malicious in ('../../etc/passwd', '2026-01-01/../../secret', 'not-a-date', ''):
            self.assertIsNone(archive.day_file_path(mac, malicious))
