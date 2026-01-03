from django import forms
from django.contrib import admin
from django.utils.translation import gettext as gettext
from django.utils.translation import gettext_lazy as _

from .models import AdsThrottleEvent, AdsThrottleOverride, SiteSetting
from .throttling import _hash_ip


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = (
        "view_repeat_window_seconds",
        "view_repeat_threshold",
        "block_seconds",
        "event_record_seconds",
        "updated_at",
    )

    def has_add_permission(self, request):
        if SiteSetting.objects.exists():
            return False
        return super().has_add_permission(request)


class AdsThrottleOverrideAdminForm(forms.ModelForm):
    APPLY_TO_USER = "user"
    APPLY_TO_IP = "ip"
    APPLY_TO_ALL = "all"

    ACTION_SHOW = "show"
    ACTION_BLOCK = "block"

    APPLY_TO_CHOICES = (
        (APPLY_TO_USER, _("Apply to user")),
        (APPLY_TO_IP, _("Apply to IP")),
        (APPLY_TO_ALL, _("Apply to all in scope")),
    )

    ACTION_CHOICES = (
        (ACTION_BLOCK, _("Block")),
        (ACTION_SHOW, _("Show")),
    )

    apply_to = forms.ChoiceField(choices=APPLY_TO_CHOICES, label=_("Apply to"))
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        initial=ACTION_BLOCK,
        label=_("Action"),
        help_text=_("Choose the action for matching viewers."),
    )
    raw_ip = forms.GenericIPAddressField(
        required=False,
        label=_("Raw IP address"),
        help_text=_(
            "Enter an IP address to compute SHA256. The raw value is not stored."
        ),
    )

    class Meta:
        model = AdsThrottleOverride
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        self.fields["scope"].help_text = _(
            "Leave empty to apply site-wide. "
            "For a specific page use the full path (for example, /courses/abc/)."
        )
        self.fields["apply_to"].help_text = _(
            "The 'all in scope' mode applies to all viewers inside the scope, "
            "or to the entire site if the scope is empty."
        )
        if "viewer_id" in self.fields:
            self.fields["viewer_id"].disabled = True
        if "force_show" in self.fields:
            self.fields["force_show"].widget = forms.HiddenInput()
        if "force_block" in self.fields:
            self.fields["force_block"].widget = forms.HiddenInput()
        if instance and instance.pk:
            if instance.user or instance.viewer_id:
                initial_apply_to = self.APPLY_TO_USER
            elif instance.ip_address_hash:
                initial_apply_to = self.APPLY_TO_IP
            else:
                initial_apply_to = self.APPLY_TO_ALL
            self.fields["apply_to"].initial = initial_apply_to
            self.fields["action"].initial = (
                self.ACTION_SHOW if instance.force_show else self.ACTION_BLOCK
            )
        else:
            self.fields["apply_to"].initial = self.APPLY_TO_USER
            self.fields["action"].initial = self.ACTION_BLOCK

    def clean(self):
        cleaned_data = super().clean()
        apply_to = cleaned_data.get("apply_to")
        raw_ip = cleaned_data.get("raw_ip")
        user = cleaned_data.get("user")
        viewer_id = cleaned_data.get("viewer_id")
        scope = (cleaned_data.get("scope") or "").strip()
        action = cleaned_data.get("action")

        if scope and not scope.startswith("/"):
            raise forms.ValidationError(
                _("Scope must be empty or start with '/'. Example: /courses/abc/.")
            )
        if action not in {self.ACTION_SHOW, self.ACTION_BLOCK}:
            raise forms.ValidationError(_("Choose an action: show or block."))
        cleaned_data["force_show"] = action == self.ACTION_SHOW
        cleaned_data["force_block"] = action == self.ACTION_BLOCK

        if apply_to == self.APPLY_TO_USER:
            if not user and not viewer_id:
                raise forms.ValidationError(
                    _("Provide a user or viewer ID for the override.")
                )
            cleaned_data["ip_address_hash"] = ""
            cleaned_data["raw_ip"] = ""
        elif apply_to == self.APPLY_TO_IP:
            if not raw_ip and not (self.instance and self.instance.ip_address_hash):
                raise forms.ValidationError(
                    _("Provide an IP address to compute the hash.")
                )
            cleaned_data["user"] = None
            cleaned_data["viewer_id"] = ""
        elif apply_to == self.APPLY_TO_ALL:
            cleaned_data["user"] = None
            cleaned_data["viewer_id"] = ""
            cleaned_data["ip_address_hash"] = ""
            cleaned_data["raw_ip"] = ""

        return cleaned_data


@admin.register(AdsThrottleOverride)
class AdsThrottleOverrideAdmin(admin.ModelAdmin):
    form = AdsThrottleOverrideAdminForm
    list_display = (
        "display_scope",
        "viewer_id",
        "user",
        "ip_address_hash",
        "force_show",
        "force_block",
        "expires_at",
        "created_at",
    )
    list_filter = ("force_show", "force_block")
    search_fields = (
        "scope",
        "viewer_id",
        "ip_address_hash",
        "user__email",
        "user__username",
    )
    readonly_fields = ("ip_address_hash", "viewer_id")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("user")

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        if search_term:
            hashed_ip = None
            try:
                import ipaddress

                ipaddress.ip_address(search_term.strip())
                hashed_ip = _hash_ip(search_term.strip())
            except ValueError:
                hashed_ip = None
            if hashed_ip:
                queryset |= self.model.objects.filter(ip_address_hash=hashed_ip)
        return queryset, use_distinct

    @admin.display(description=_("Scope"))
    def display_scope(self, obj):
        return obj.scope or gettext("All")

    def save_model(self, request, obj, form, change):
        apply_to = form.cleaned_data.get("apply_to")
        raw_ip = form.cleaned_data.get("raw_ip")
        if apply_to == AdsThrottleOverrideAdminForm.APPLY_TO_IP:
            if raw_ip:
                obj.ip_address_hash = _hash_ip(raw_ip)
            obj.user = None
            obj.viewer_id = ""
        elif apply_to == AdsThrottleOverrideAdminForm.APPLY_TO_ALL:
            obj.user = None
            obj.viewer_id = ""
            obj.ip_address_hash = ""
        else:
            obj.ip_address_hash = ""
            if obj.user:
                obj.viewer_id = f"user:{obj.user.pk}"
        super().save_model(request, obj, form, change)


@admin.register(AdsThrottleEvent)
class AdsThrottleEventAdmin(admin.ModelAdmin):
    list_display = (
        "display_scope",
        "viewer_hash",
        "ip_address_hash",
        "count",
        "blocked",
        "first_seen",
        "last_seen",
    )
    list_filter = ("blocked",)
    search_fields = ("scope", "viewer_hash", "ip_address_hash")
    ordering = ("-last_seen",)
    readonly_fields = (
        "scope",
        "viewer_hash",
        "ip_address_hash",
        "first_seen",
        "last_seen",
        "count",
        "blocked",
    )
    date_hierarchy = "last_seen"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        if search_term:
            hashed_ip = None
            try:
                import ipaddress

                ipaddress.ip_address(search_term.strip())
                hashed_ip = _hash_ip(search_term.strip())
            except ValueError:
                hashed_ip = None
            if hashed_ip:
                queryset |= self.model.objects.filter(ip_address_hash=hashed_ip)
        return queryset, use_distinct

    @admin.display(description=_("Scope"))
    def display_scope(self, obj):
        return obj.scope or gettext("All")
