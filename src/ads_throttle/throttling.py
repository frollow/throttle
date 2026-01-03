import hashlib

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.core.cache import cache
from django.db import models
from django.db.models import Case, IntegerField, Max, Q, QuerySet, When
from django.http import HttpRequest
from django.utils import timezone

from .models import AdsThrottleEvent, AdsThrottleOverride, SiteSetting

DEFAULT_VIEW_REPEAT_WINDOW_SECONDS = 600
DEFAULT_VIEW_REPEAT_THRESHOLD = 20
DEFAULT_BLOCK_SECONDS = 3600
DEFAULT_SETTINGS_CACHE_SECONDS = 300
DEFAULT_EVENT_RECORD_SECONDS = 60

UserIdentity = AbstractBaseUser | AnonymousUser


def _get_settings_values() -> dict[str, int]:
    """Return throttle configuration values merged from cache and defaults."""
    cache_key = "ads_throttle:settings"
    cache_ttl = getattr(
        settings, "ADS_THROTTLE_SETTINGS_CACHE_SECONDS", DEFAULT_SETTINGS_CACHE_SECONDS
    )
    stored = SiteSetting.get_cached(cache, cache_key, cache_ttl)
    if stored:
        return stored
    return {
        "view_repeat_window_seconds": getattr(
            settings,
            "ADS_VIEW_REPEAT_WINDOW_SECONDS",
            DEFAULT_VIEW_REPEAT_WINDOW_SECONDS,
        ),
        "view_repeat_threshold": getattr(
            settings, "ADS_VIEW_REPEAT_THRESHOLD", DEFAULT_VIEW_REPEAT_THRESHOLD
        ),
        "block_seconds": getattr(settings, "ADS_BLOCK_SECONDS", DEFAULT_BLOCK_SECONDS),
        "event_record_seconds": getattr(
            settings,
            "ADS_THROTTLE_EVENT_RECORD_SECONDS",
            DEFAULT_EVENT_RECORD_SECONDS,
        ),
    }


def _viewer_id(request: HttpRequest) -> str:
    """Build a stable identifier for the current viewer."""
    user = request.user
    session_key = request.session.session_key
    if not session_key:
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
    if user.is_authenticated:
        return f"user:{user.pk}"
    if session_key:
        return f"session:{session_key}"
    return "anonymous"


def _viewer_fingerprint(request: HttpRequest) -> str:
    """Build a stable fingerprint string for the current viewer."""
    viewer_id = _viewer_id(request)
    ip_address = request.META.get("REMOTE_ADDR", "")
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return f"{viewer_id}:{ip_address}:{user_agent}"


def _get_client_ip(request: HttpRequest) -> str:
    """Determine the client IP address using trusted headers when present."""
    header_name = getattr(settings, "ADS_THROTTLE_IP_HEADER", "").upper()
    if header_name:
        custom_ip = request.META.get(f"HTTP_{header_name}")
        if custom_ip:
            return custom_ip.strip()
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP", "")
    if real_ip:
        return real_ip.strip()
    return request.META.get("REMOTE_ADDR", "")


def _hash_ip(ip_address: str) -> str:
    """Return a deterministic hash of the IP address for privacy."""
    if not ip_address:
        return ""
    return hashlib.sha256(ip_address.strip().encode("utf-8")).hexdigest()


def _find_override(
    user: UserIdentity | None,
    viewer_id: str,
    ip_address_hash: str,
    scope_value: str,
) -> QuerySet[AdsThrottleOverride] | None:
    """Find throttle overrides that match the supplied identifiers."""
    scope_filter = Q(scope__isnull=True) | Q(scope="") | Q(scope=scope_value)
    identifier_filter = Q(user__isnull=True, viewer_id="", ip_address_hash="")
    if user and user.is_authenticated:
        identifier_filter |= Q(user=user)
    if viewer_id:
        identifier_filter |= Q(viewer_id=viewer_id)
    if ip_address_hash:
        identifier_filter |= Q(ip_address_hash=ip_address_hash)
    if not identifier_filter:
        return None
    now = timezone.now()
    return AdsThrottleOverride.objects.filter(
        scope_filter,
        identifier_filter,
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
    )


def _get_override_decision(
    user: UserIdentity | None,
    viewer_id: str,
    ip_address_hash: str,
    scope_value: str,
) -> str | None:
    """Resolve an explicit override decision for a viewer."""
    if not (viewer_id or ip_address_hash or (user and user.is_authenticated)):
        return None
    scope_hash = hashlib.sha256(scope_value.encode("utf-8")).hexdigest()
    user_id = user.pk if user and user.is_authenticated else ""
    cache_key = (
        f"ads_throttle:override:{scope_hash}:{viewer_id}:{user_id}:{ip_address_hash}"
    )
    cache_ttl = getattr(settings, "ADS_THROTTLE_OVERRIDE_CACHE_SECONDS", 60)
    cached = cache.get(cache_key)
    if cached:
        return None if cached == "none" else cached
    override_qs = _find_override(user, viewer_id, ip_address_hash, scope_value)
    if override_qs is None:
        return None
    flags = override_qs.aggregate(
        force_block=Max(
            Case(When(force_block=True, then=1), default=0, output_field=IntegerField())
        ),
        force_show=Max(
            Case(When(force_show=True, then=1), default=0, output_field=IntegerField())
        ),
    )
    decision = None
    if flags["force_block"]:
        decision = "block"
    elif flags["force_show"]:
        decision = "show"
    cache.set(cache_key, decision or "none", timeout=cache_ttl)
    return decision


def _record_event(
    scope_value: str,
    viewer_hash: str,
    ip_address_hash: str,
    blocked: bool,
) -> None:
    """Upsert a throttle event record for analytics and auditing."""
    now = timezone.now()
    event, created = AdsThrottleEvent.objects.get_or_create(
        scope=scope_value,
        viewer_hash=viewer_hash,
        defaults={
            "first_seen": now,
            "last_seen": now,
            "count": 1,
            "blocked": blocked,
            "ip_address_hash": ip_address_hash,
        },
    )
    if created:
        return
    update_fields = {"last_seen": now, "count": models.F("count") + 1}
    if blocked:
        update_fields["blocked"] = True
    if ip_address_hash and not event.ip_address_hash:
        update_fields["ip_address_hash"] = ip_address_hash
    AdsThrottleEvent.objects.filter(pk=event.pk).update(**update_fields)


def _should_record_event(
    scope_hash: str,
    viewer_hash: str,
    blocked: bool,
    record_seconds: int,
) -> bool:
    """Rate-limit event recording for a viewer and scope."""
    cache_key = f"ads_throttle:event:{scope_hash}:{viewer_hash}:{int(blocked)}"
    return cache.add(cache_key, True, timeout=record_seconds)


def should_show_ads(request: HttpRequest | None, scope: str | None = None) -> bool:
    """Return whether ads should be shown for the current request."""
    if not request:
        return True
    scope_value = scope or request.path
    viewer_fingerprint = _viewer_fingerprint(request)
    viewer_hash = hashlib.sha256(viewer_fingerprint.encode("utf-8")).hexdigest()
    scope_hash = hashlib.sha256(scope_value.encode("utf-8")).hexdigest()

    viewer_id = _viewer_id(request)
    ip_address_hash = _hash_ip(_get_client_ip(request))
    settings_values = _get_settings_values()
    override_decision = _get_override_decision(
        request.user,
        viewer_id,
        ip_address_hash,
        scope_value,
    )
    if override_decision == "block":
        if _should_record_event(
            scope_hash,
            viewer_hash,
            True,
            settings_values["event_record_seconds"],
        ):
            _record_event(scope_value, viewer_hash, ip_address_hash, True)
        return False
    if override_decision == "show":
        return True
    ads_window_seconds = settings_values["view_repeat_window_seconds"]
    ads_threshold = settings_values["view_repeat_threshold"]
    ads_block_seconds = settings_values["block_seconds"]

    count_key = f"ads:views:{scope_hash}:{viewer_hash}"
    block_key = f"ads:block:{scope_hash}:{viewer_hash}"

    if cache.get(block_key):
        if _should_record_event(
            scope_hash,
            viewer_hash,
            True,
            settings_values["event_record_seconds"],
        ):
            _record_event(scope_value, viewer_hash, ip_address_hash, True)
        return False

    if cache.add(count_key, 1, timeout=ads_window_seconds):
        return True

    count = cache.incr(count_key)
    if count > ads_threshold:
        cache.set(block_key, True, timeout=ads_block_seconds)
        if _should_record_event(
            scope_hash,
            viewer_hash,
            True,
            settings_values["event_record_seconds"],
        ):
            _record_event(scope_value, viewer_hash, ip_address_hash, True)
        return False
    return True
