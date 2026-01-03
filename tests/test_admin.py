from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase

from ads_throttle.admin import (
    AdsThrottleEventAdmin,
    AdsThrottleOverrideAdmin,
    AdsThrottleOverrideAdminForm,
    SiteSettingAdmin,
)
from ads_throttle.models import AdsThrottleEvent, AdsThrottleOverride, SiteSetting
from ads_throttle.throttling import _hash_ip
from tests.utils import build_request


class AdsThrottleOverrideAdminFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="form-user",
            password="pass",
        )

    def test_apply_to_user_requires_user_or_viewer_id(self):
        form = AdsThrottleOverrideAdminForm(
            data={"apply_to": "user", "action": "block", "scope": ""}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Provide a user", form.non_field_errors()[0])

    def test_apply_to_ip_requires_raw_ip(self):
        form = AdsThrottleOverrideAdminForm(
            data={"apply_to": "ip", "action": "block", "scope": ""}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Provide an IP address", form.non_field_errors()[0])

    def test_scope_must_start_with_slash_when_not_empty(self):
        form = AdsThrottleOverrideAdminForm(
            data={"apply_to": "all", "action": "block", "scope": "bad"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Scope must be empty", form.non_field_errors()[0])

    def test_action_sets_force_flags(self):
        form = AdsThrottleOverrideAdminForm(
            data={"apply_to": "all", "action": "show", "scope": ""}
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["force_show"])
        self.assertFalse(form.cleaned_data["force_block"])

    def test_apply_to_all_clears_identifiers(self):
        form = AdsThrottleOverrideAdminForm(
            data={
                "apply_to": "all",
                "action": "block",
                "scope": "",
                "user": self.user.pk,
                "raw_ip": "1.2.3.4",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["user"])
        self.assertEqual(form.cleaned_data["viewer_id"], "")
        self.assertEqual(form.cleaned_data["ip_address_hash"], "")
        self.assertEqual(form.cleaned_data["raw_ip"], "")


class AdsThrottleOverrideAdminSaveTests(TestCase):
    def setUp(self):
        self.admin_site = admin.sites.AdminSite()
        self.admin = AdsThrottleOverrideAdmin(AdsThrottleOverride, self.admin_site)
        self.superuser = get_user_model().objects.create_superuser(
            username="admin",
            password="pass",
            email="admin@example.com",
        )
        self.user = get_user_model().objects.create_user(
            username="regular",
            password="pass",
        )
        self.request = build_request(user=self.superuser)

    def test_save_model_applies_ip_hash(self):
        form = AdsThrottleOverrideAdminForm(
            data={
                "apply_to": "ip",
                "action": "block",
                "scope": "/",
                "raw_ip": "1.2.3.4",
            }
        )
        self.assertTrue(form.is_valid())
        obj = form.save(commit=False)
        self.admin.save_model(self.request, obj, form, change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.ip_address_hash, _hash_ip("1.2.3.4"))
        self.assertIsNone(obj.user)
        self.assertEqual(obj.viewer_id, "")

    def test_save_model_clears_all_identifiers(self):
        form = AdsThrottleOverrideAdminForm(
            data={
                "apply_to": "all",
                "action": "show",
                "scope": "/",
                "user": self.user.pk,
            }
        )
        self.assertTrue(form.is_valid())
        obj = form.save(commit=False)
        self.admin.save_model(self.request, obj, form, change=False)
        obj.refresh_from_db()
        self.assertIsNone(obj.user)
        self.assertEqual(obj.viewer_id, "")
        self.assertEqual(obj.ip_address_hash, "")

    def test_save_model_sets_viewer_id_for_user(self):
        form = AdsThrottleOverrideAdminForm(
            data={
                "apply_to": "user",
                "action": "block",
                "scope": "/",
                "user": self.user.pk,
            }
        )
        self.assertTrue(form.is_valid())
        obj = form.save(commit=False)
        self.admin.save_model(self.request, obj, form, change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.viewer_id, f"user:{self.user.pk}")
        self.assertEqual(obj.ip_address_hash, "")


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.admin_site = admin.sites.AdminSite()
        self.superuser = get_user_model().objects.create_superuser(
            username="super",
            password="pass",
            email="super@example.com",
        )
        self.user = get_user_model().objects.create_user(
            username="user",
            password="pass",
        )

    def test_site_setting_admin_add_permission(self):
        site_admin = SiteSettingAdmin(SiteSetting, self.admin_site)
        request = build_request(user=self.superuser)
        self.assertTrue(site_admin.has_add_permission(request))
        SiteSetting.objects.create()
        self.assertFalse(site_admin.has_add_permission(request))

    def test_event_admin_permissions(self):
        event_admin = AdsThrottleEventAdmin(AdsThrottleEvent, self.admin_site)
        request = build_request(user=self.user)
        self.assertFalse(event_admin.has_add_permission(request))
        self.assertFalse(event_admin.has_change_permission(request))
        self.assertFalse(event_admin.has_delete_permission(request))

        super_request = build_request(user=self.superuser)
        self.assertTrue(event_admin.has_delete_permission(super_request))
