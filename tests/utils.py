from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory


def build_request(
    path="/",
    *,
    user=None,
    with_session=True,
    meta=None,
    cookies=None,
):
    factory = RequestFactory()
    request = factory.get(path)
    if meta:
        request.META.update(meta)
    request.user = user or AnonymousUser()
    if with_session:
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
    else:
        request.session = SimpleNamespace(session_key=None)
    if cookies:
        request.COOKIES.update(cookies)
    return request
