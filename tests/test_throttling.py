import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from ads_throttle.models import (AdsThrottleEvent, AdsThrottleOverride,
                                 SiteSetting)
from ads_throttle.throttling import (_get_client_ip, _get_override_decision,
                                     _get_settings_values, _hash_ip,
                                     _record_event, _should_record_event,
                                     _viewer_id, should_show_ads)
from tests.utils import build_request


class SettingsValuesTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(
        ADS_VIEW_REPEAT_WINDOW_SECONDS=111,
        ADS_VIEW_REPEAT_THRESHOLD=7,
        ADS_BLOCK_SECONDS=99,
        ADS_THROTTLE_EVENT_RECORD_SECONDS=12,
    )
    def test_falls_back_to_settings_when_no_site_setting(self):
        values = _get_settings_values()
        self.assertEqual(values["view_repeat_window_seconds"], 111)
        self.assertEqual(values["view_repeat_threshold"], 7)
        self.assertEqual(values["block_seconds"], 99)
        self.assertEqual(values["event_record_seconds"], 12)

    @override_settings(
        ADS_VIEW_REPEAT_WINDOW_SECONDS=1,
        ADS_VIEW_REPEAT_THRESHOLD=1,
        ADS_BLOCK_SECONDS=1,
        ADS_THROTTLE_EVENT_RECORD_SECONDS=1,
    )
    def test_prefers_site_setting_when_present(self):
        SiteSetting.objects.create(
            view_repeat_window_seconds=555,
            view_repeat_threshold=9,
            block_seconds=321,
            event_record_seconds=33,
        )
        values = _get_settings_values()
        self.assertEqual(values["view_repeat_window_seconds"], 555)
        self.assertEqual(values["view_repeat_threshold"], 9)
        self.assertEqual(values["block_seconds"], 321)
        self.assertEqual(values["event_record_seconds"], 33)


class ViewerIdTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="viewer",
            password="pass",
        )

    def test_authenticated_user_prefers_user_id(self):
        request = build_request(user=self.user)
        self.assertEqual(_viewer_id(request), f"user:{self.user.pk}")

    def test_session_key_used_for_anonymous(self):
        request = build_request(user=AnonymousUser())
        session_key = request.session.session_key
        self.assertEqual(_viewer_id(request), f"session:{session_key}")

    def test_cookie_used_when_session_key_missing(self):
        request = build_request(with_session=False)
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "cookie-session"
        self.assertEqual(_viewer_id(request), "session:cookie-session")


class ClientIpTests(SimpleTestCase):
    @override_settings(ADS_THROTTLE_IP_HEADER="X_REAL_IP")
    def test_uses_custom_header_when_configured(self):
        request = build_request(
            meta={"HTTP_X_REAL_IP": " 10.0.0.5 "}, with_session=False
        )
        self.assertEqual(_get_client_ip(request), "10.0.0.5")

    def test_uses_first_forwarded_for_ip(self):
        request = build_request(
            meta={"HTTP_X_FORWARDED_FOR": " 1.1.1.1, 2.2.2.2 "},
            with_session=False,
        )
        self.assertEqual(_get_client_ip(request), "1.1.1.1")

    def test_uses_real_ip_when_forwarded_for_missing(self):
        request = build_request(meta={"HTTP_X_REAL_IP": "9.9.9.9"}, with_session=False)
        self.assertEqual(_get_client_ip(request), "9.9.9.9")

    def test_falls_back_to_remote_addr(self):
        request = build_request(meta={"REMOTE_ADDR": "8.8.8.8"}, with_session=False)
        self.assertEqual(_get_client_ip(request), "8.8.8.8")


class HashIpTests(SimpleTestCase):
    def test_hash_ip_returns_empty_for_blank(self):
        self.assertEqual(_hash_ip(""), "")

    def test_hash_ip_returns_sha256_hex(self):
        expected = hashlib.sha256("127.0.0.1".encode("utf-8")).hexdigest()
        self.assertEqual(_hash_ip("127.0.0.1"), expected)


class OverrideDecisionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="override",
            password="pass",
        )

    def test_force_block_wins_over_force_show(self):
        scope = "/offers/"
        viewer_id = f"user:{self.user.pk}"
        ip_hash = _hash_ip("10.0.0.1")
        AdsThrottleOverride.objects.create(
            scope=scope,
            user=self.user,
            force_show=True,
        )
        AdsThrottleOverride.objects.create(
            scope=scope,
            viewer_id=viewer_id,
            force_block=True,
        )
        decision = _get_override_decision(self.user, viewer_id, ip_hash, scope)
        self.assertEqual(decision, "block")

    def test_expired_override_is_ignored(self):
        scope = "/news/"
        viewer_id = f"user:{self.user.pk}"
        AdsThrottleOverride.objects.create(
            scope=scope,
            user=self.user,
            force_block=True,
            expires_at=timezone.now() - timedelta(days=1),
        )
        decision = _get_override_decision(self.user, viewer_id, "", scope)
        self.assertIsNone(decision)

    def test_cached_none_skips_database(self):
        scope = "/cached/"
        viewer_id = "session:abc"
        ip_hash = _hash_ip("1.2.3.4")
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        cache_key = f"ads_throttle:override:{scope_hash}:{viewer_id}::{ip_hash}"
        cache.set(cache_key, "none", timeout=60)
        with self.assertNumQueries(0):
            decision = _get_override_decision(
                AnonymousUser(),
                viewer_id,
                ip_hash,
                scope,
            )
        self.assertIsNone(decision)


class EventRecordingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_should_record_event_rate_limits(self):
        self.assertTrue(_should_record_event("scope", "viewer", True, 60))
        self.assertFalse(_should_record_event("scope", "viewer", True, 60))

    def test_record_event_updates_existing(self):
        _record_event("scope", "viewer", "", False)
        event = AdsThrottleEvent.objects.get(scope="scope", viewer_hash="viewer")
        self.assertEqual(event.count, 1)
        self.assertFalse(event.blocked)

        ip_hash = _hash_ip("3.3.3.3")
        _record_event("scope", "viewer", ip_hash, True)
        event.refresh_from_db()
        self.assertEqual(event.count, 2)
        self.assertTrue(event.blocked)
        self.assertEqual(event.ip_address_hash, ip_hash)


class ShouldShowAdsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="ads",
            password="pass",
        )

    def test_returns_true_without_request(self):
        self.assertTrue(should_show_ads(None))

    def test_override_show_short_circuits(self):
        scope = "/promo/"
        request = build_request(
            path=scope,
            user=self.user,
            meta={"REMOTE_ADDR": "10.10.10.10", "HTTP_USER_AGENT": "ua"},
        )
        AdsThrottleOverride.objects.create(
            scope=scope,
            user=self.user,
            force_show=True,
        )
        self.assertTrue(should_show_ads(request))
        self.assertFalse(AdsThrottleEvent.objects.exists())

    def test_override_block_records_event(self):
        scope = "/blocked/"
        request = build_request(
            path=scope,
            user=self.user,
            meta={"REMOTE_ADDR": "10.10.10.11", "HTTP_USER_AGENT": "ua"},
        )
        AdsThrottleOverride.objects.create(
            scope=scope,
            user=self.user,
            force_block=True,
        )
        self.assertFalse(should_show_ads(request))
        event = AdsThrottleEvent.objects.get(scope=scope)
        self.assertTrue(event.blocked)
        self.assertEqual(event.count, 1)

    @override_settings(
        ADS_VIEW_REPEAT_WINDOW_SECONDS=60,
        ADS_VIEW_REPEAT_THRESHOLD=1,
        ADS_BLOCK_SECONDS=60,
        ADS_THROTTLE_EVENT_RECORD_SECONDS=60,
    )
    def test_blocks_after_threshold_and_rate_limits_events(self):
        scope = "/cycle/"
        request = build_request(
            path=scope,
            meta={"REMOTE_ADDR": "10.10.10.12", "HTTP_USER_AGENT": "ua"},
        )
        self.assertTrue(should_show_ads(request))
        self.assertFalse(should_show_ads(request))
        self.assertFalse(should_show_ads(request))
        event = AdsThrottleEvent.objects.get(scope=scope)
        self.assertEqual(event.count, 1)
