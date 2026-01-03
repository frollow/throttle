from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AdsThrottleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ads_throttle"
    verbose_name = _("Ads throttle")
