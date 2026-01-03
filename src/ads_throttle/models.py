from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as gettext
from django.utils.translation import gettext_lazy as _


class SiteSetting(models.Model):
    view_repeat_window_seconds = models.PositiveIntegerField(
        default=600,
        verbose_name=_("View window (seconds)"),
        help_text=_("Time window in seconds for counting ad impressions."),
    )
    view_repeat_threshold = models.PositiveIntegerField(
        default=20,
        verbose_name=_("View threshold"),
        help_text=_(
            "How many ad impressions are allowed within the window before blocking."
        ),
    )
    block_seconds = models.PositiveIntegerField(
        default=3600,
        verbose_name=_("Block duration (seconds)"),
        help_text=_(
            "How long to block ads after the threshold is reached, in seconds."
        ),
    )
    event_record_seconds = models.PositiveIntegerField(
        default=60,
        verbose_name=_("Event record interval (seconds)"),
        help_text=_(
            "How often (in seconds) to update block counters for a single viewer/page pair."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Ads throttle setting")
        verbose_name_plural = _("Ads throttle settings")

    def __str__(self):
        return gettext("Ads throttle settings")

    @classmethod
    def get_cached(cls, cache, cache_key, timeout):
        cached = cache.get(cache_key)
        if cached:
            return cached
        instance = cls.objects.first()
        if not instance:
            return None
        data = {
            "view_repeat_window_seconds": instance.view_repeat_window_seconds,
            "view_repeat_threshold": instance.view_repeat_threshold,
            "block_seconds": instance.block_seconds,
            "event_record_seconds": instance.event_record_seconds,
        }
        cache.set(cache_key, data, timeout=timeout)
        return data


class AdsThrottleOverride(models.Model):
    scope = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("Scope"),
        help_text=_("Page path or empty to apply site-wide."),
    )
    viewer_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Viewer ID"),
        help_text=_("Format: user:<id> or session:<key>."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("User"),
        related_name="ads_throttle_overrides",
    )
    ip_address_hash = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("IP address hash"),
        help_text=_("SHA256 hash of the IP address."),
    )
    force_show = models.BooleanField(default=False, verbose_name=_("Force show"))
    force_block = models.BooleanField(default=False, verbose_name=_("Force block"))
    expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Expires at")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Ads throttle override")
        verbose_name_plural = _("Ads throttle overrides")
        indexes = [
            models.Index(
                fields=["scope", "viewer_id", "expires_at"],
                name="ads_thrott_scope_1ff7d4_idx",
            ),
            models.Index(
                fields=["scope", "ip_address_hash", "expires_at"],
                name="ads_thrott_scope_a6fb08_idx",
            ),
            models.Index(
                fields=["scope", "user", "expires_at"],
                name="ads_thrott_scope_f40e50_idx",
            ),
        ]

    def __str__(self):
        target = (
            self.viewer_id
            or (self.user.username if self.user_id else None)
            or self.ip_address_hash
        )
        if not target:
            target = gettext("all viewers")
        scope = self.scope or gettext("all scopes")
        return gettext("Override for %(target)s (%(scope)s)") % {
            "target": target,
            "scope": scope,
        }

    def is_active(self):
        if not self.expires_at:
            return True
        return self.expires_at > timezone.now()


class AdsThrottleEvent(models.Model):
    scope = models.CharField(max_length=512, verbose_name=_("Scope"))
    viewer_hash = models.CharField(max_length=64, verbose_name=_("Viewer hash"))
    ip_address_hash = models.CharField(
        max_length=64, blank=True, verbose_name=_("IP address hash")
    )
    first_seen = models.DateTimeField(verbose_name=_("First seen"))
    last_seen = models.DateTimeField(verbose_name=_("Last seen"))
    count = models.PositiveIntegerField(default=0, verbose_name=_("Count"))
    blocked = models.BooleanField(default=False, verbose_name=_("Blocked"))

    class Meta:
        verbose_name = _("Ads throttle event")
        verbose_name_plural = _("Ads throttle events")
        indexes = [
            models.Index(fields=["scope", "blocked", "last_seen"]),
            models.Index(fields=["viewer_hash"]),
            models.Index(fields=["ip_address_hash"]),
        ]
        unique_together = ("scope", "viewer_hash")

    def __str__(self):
        scope = self.scope or gettext("all scopes")
        return gettext("Ads throttle event (%(scope)s)") % {"scope": scope}
