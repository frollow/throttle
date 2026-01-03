from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ads_throttle.models import AdsThrottleOverride, SiteSetting


class SiteSettingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_cached_reads_from_database_and_sets_cache(self):
        setting = SiteSetting.objects.create(
            view_repeat_window_seconds=123,
            view_repeat_threshold=7,
            block_seconds=321,
            event_record_seconds=11,
        )
        cache_key = "ads_throttle:settings"
        data = SiteSetting.get_cached(cache, cache_key, timeout=60)
        self.assertEqual(
            data,
            {
                "view_repeat_window_seconds": setting.view_repeat_window_seconds,
                "view_repeat_threshold": setting.view_repeat_threshold,
                "block_seconds": setting.block_seconds,
                "event_record_seconds": setting.event_record_seconds,
            },
        )
        self.assertEqual(cache.get(cache_key), data)

    def test_get_cached_skips_database_when_cached(self):
        cache_key = "ads_throttle:settings"
        cached = {
            "view_repeat_window_seconds": 1,
            "view_repeat_threshold": 2,
            "block_seconds": 3,
            "event_record_seconds": 4,
        }
        cache.set(cache_key, cached, timeout=60)
        with self.assertNumQueries(0):
            data = SiteSetting.get_cached(cache, cache_key, timeout=60)
        self.assertEqual(data, cached)

    def test_get_cached_returns_none_when_missing(self):
        cache_key = "ads_throttle:settings"
        self.assertIsNone(SiteSetting.get_cached(cache, cache_key, timeout=60))


class AdsThrottleOverrideTests(TestCase):
    def test_is_active_true_without_expiry(self):
        override = AdsThrottleOverride.objects.create(
            scope="/",
            viewer_id="viewer",
            force_block=True,
        )
        self.assertTrue(override.is_active())

    def test_is_active_false_when_expired(self):
        override = AdsThrottleOverride.objects.create(
            scope="/",
            viewer_id="viewer",
            force_block=True,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(override.is_active())

    def test_is_active_true_when_expiry_in_future(self):
        override = AdsThrottleOverride.objects.create(
            scope="/",
            viewer_id="viewer",
            force_block=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(override.is_active())
