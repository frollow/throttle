from unittest.mock import patch

from django.test import SimpleTestCase

from ads_throttle.context_processors import ads
from tests.utils import build_request


class ContextProcessorTests(SimpleTestCase):
    def test_ads_injects_show_ads_flag(self):
        request = build_request(path="/context/", with_session=False)
        with patch(
            "ads_throttle.context_processors.should_show_ads",
            return_value=False,
        ) as mock_should_show:
            context = ads(request)
        self.assertEqual(context, {"show_ads": False})
        mock_should_show.assert_called_once_with(request)
