from collections.abc import Mapping
from typing import cast

from django import template
from django.http import HttpRequest

from ads_throttle.throttling import should_show_ads

register = template.Library()


def _should_show_ads_cached(
    request: HttpRequest | None, scope: str | None = None
) -> bool:
    if not request:
        return should_show_ads(request, scope)
    scope_value = scope or request.path
    cache = getattr(request, "_ads_throttle_cache", None)
    if cache is None:
        cache = {}
        setattr(request, "_ads_throttle_cache", cache)
    if scope_value in cache:
        return cache[scope_value]
    decision = should_show_ads(request, scope)
    cache[scope_value] = decision
    return decision


@register.simple_tag(takes_context=True)
def show_ads(context: Mapping[str, object], scope: str | None = None) -> bool:
    """Return whether ads should be shown for this template render.

    The decision is cached on the request object for the lifetime of the
    current HTTP request so multiple ad partials can share it without
    affecting cross-request throttling behavior.
    """
    request = context.get("request")
    request = cast(HttpRequest | None, request)
    return _should_show_ads_cached(request, scope)


@register.filter(name="should_show_ads")
def should_show_ads_filter(
    request: HttpRequest | None, scope: str | None = None
) -> bool:
    """Template filter wrapper around should_show_ads with per-request cache."""
    return _should_show_ads_cached(request, scope)
