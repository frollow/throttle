from unittest.mock import patch

from django.test import SimpleTestCase

from ads_throttle.templatetags.ads_throttle_tags import show_ads, should_show_ads_filter
from tests.utils import build_request


class TemplateTagsTests(SimpleTestCase):
    def test_show_ads_caches_per_scope_on_request(self):
        request = build_request(path="/articles/", with_session=False)
        context = {"request": request}
        with patch(
            "ads_throttle.templatetags.ads_throttle_tags.should_show_ads",
            return_value=True,
        ) as mock_should_show:
            self.assertTrue(show_ads(context, scope="/articles/"))
            self.assertTrue(show_ads(context, scope="/articles/"))
        mock_should_show.assert_called_once_with(request, "/articles/")

    def test_show_ads_separates_scopes(self):
        request = build_request(path="/articles/", with_session=False)
        context = {"request": request}
        with patch(
            "ads_throttle.templatetags.ads_throttle_tags.should_show_ads",
            return_value=True,
        ) as mock_should_show:
            self.assertTrue(show_ads(context, scope="/a/"))
            self.assertTrue(show_ads(context, scope="/b/"))
        self.assertEqual(mock_should_show.call_count, 2)

    def test_filter_shares_cache(self):
        request = build_request(path="/articles/", with_session=False)
        with patch(
            "ads_throttle.templatetags.ads_throttle_tags.should_show_ads",
            return_value=True,
        ) as mock_should_show:
            self.assertTrue(should_show_ads_filter(request, scope="/articles/"))
            self.assertTrue(should_show_ads_filter(request, scope="/articles/"))
        mock_should_show.assert_called_once_with(request, "/articles/")
