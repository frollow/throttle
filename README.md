# ads_throttle — Django Ads Throttling & Frequency Capping

`ads_throttle` is a Django app that limits ad impressions per viewer within a
time window and lets admins override decisions in the admin UI.

## How it works

1. A viewer fingerprint is computed (user/session + IP + User-Agent).
2. A per-scope counter is stored in cache (scope defaults to `request.path`).
3. When the threshold is exceeded, ads are blocked for a configured duration.
4. Overrides can force show/block for specific viewers or scopes.

## Installation

```bash
pip install ads-throttle
```

Add the app and (optionally) the context processor (use it when ads appear on every page):

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "ads_throttle",
]

TEMPLATES = [
    {
        "OPTIONS": {
            "context_processors": [
                # ...
                "ads_throttle.context_processors.ads",
            ],
        },
    },
]
```

Run migrations:

```bash
python manage.py migrate
```

## Usage

Templates with the context processor (best when ads are shown on every page):

```django
{% if show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

Templates with tag/filter (best when ads are only on some pages, so other pages avoid extra checks):

```django
{% load ads_throttle_tags %}
{% show_ads as show_ads %}
{% if show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

```django
{% if request|should_show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

When using tags/filters, you can omit the context processor to avoid running the check on pages without ads.

Python:

```python
from ads_throttle.throttling import should_show_ads

if should_show_ads(request, scope="/landing/"):
    ...
```

## Settings

Settings can be provided via `settings.py` or in the `Ads throttle settings`
admin record (admin settings take precedence when present).

- `ADS_VIEW_REPEAT_WINDOW_SECONDS` — window for counting impressions (seconds).
- `ADS_VIEW_REPEAT_THRESHOLD` — max impressions allowed within the window.
- `ADS_BLOCK_SECONDS` — block duration after the limit is reached (seconds).
- `ADS_THROTTLE_EVENT_RECORD_SECONDS` — event recording interval (seconds).
- `ADS_THROTTLE_SETTINGS_CACHE_SECONDS` — settings cache TTL (seconds).
- `ADS_THROTTLE_OVERRIDE_CACHE_SECONDS` — override cache TTL (seconds).
- `ADS_THROTTLE_IP_HEADER` — header name that carries the real client IP (optional).

## Admin fields

### Ads throttle settings

Single global record with throttle parameters:

- **View window (seconds)** — time window for counting impressions.
- **View threshold** — max impressions within the window before blocking.
- **Block duration (seconds)** — how long to block after the threshold.
- **Event record interval (seconds)** — how often to update block counters for a single viewer/page pair.
- **Updated at** — last update timestamp.

### Ads throttle overrides

Manual overrides:

- **Scope** — page path (`/courses/abc/`) or empty for site-wide.
- **Apply to** — apply to user, IP, or all in scope.
- **Action** — show or block.
- **User** — user record (for user rules).
- **Viewer ID** — `user:<id>` or `session:<key>`.
- **Raw IP address** — raw IP used to compute hash.
- **IP address hash** — SHA256 hash (read-only). Raw IP values are not stored.
- **Expires at** — when the rule expires.
- **Created at / Updated at** — metadata.

### Ads throttle events

Block event log:

- **Scope** — page path.
- **Viewer hash** — hashed viewer fingerprint.
- **IP address hash** — SHA256 hash of IP.
- **First seen / Last seen** — first/last seen timestamps.
- **Count** — number of events recorded.
- **Blocked** — whether it was blocked.

## Localization

The app supports English (default) and Russian. Admin language follows Django’s
active locale (`LANGUAGE_CODE` with `LocaleMiddleware`).

## Documentation

Full documentation is available in `/docs`.
