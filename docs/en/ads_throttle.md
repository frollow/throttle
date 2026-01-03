# Documentation: ads_throttle

`ads_throttle` is a Django app that throttles ad impressions per viewer within a
time window and lets admins override the decision manually.

## Use cases

- Reduce excessive ad impressions for a single viewer.
- Force allow/block for a specific user, session, or IP.
- Record blocking events for analytics.

## Architecture

Key parts:

- **Models** (`ads_throttle/models.py`)
  - `SiteSetting` — global throttling parameters.
  - `AdsThrottleOverride` — manual overrides.
  - `AdsThrottleEvent` — event log.
- **Throttling logic** (`ads_throttle/throttling.py`)
  - `should_show_ads` — the main decision function.
- **Context processor** (`ads_throttle/context_processors.py`)
  - injects `show_ads` into templates.
- **Template tags/filters** (`ads_throttle/templatetags/ads_throttle_tags.py`)
  - `show_ads` tag and `should_show_ads` filter for selective use.
- **Admin** (`ads_throttle/admin.py`)
  - admin forms, filters, and display helpers.

## Requirements

- A database for Django models (e.g., PostgreSQL, MySQL, or SQLite for local dev).
- A cache backend that supports `add` and `incr` (e.g., Redis, Memcached, or
  database cache). For production, Redis or Memcached is recommended.

## Installation

```bash
pip install ads-throttle
```

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "ads_throttle",
]

MIDDLEWARE = [
    "django.middleware.locale.LocaleMiddleware",
    # ...
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

```bash
python manage.py migrate
```

## Quick start

Templates with the context processor (best when ads are shown on every page):

```django
{% if show_ads %}
  <!-- ad block -->
{% endif %}
```

Templates with tags/filters (best when ads are only on some pages, so other pages avoid the check):

```django
{% load ads_throttle_tags %}
{% show_ads as show_ads %}
{% if show_ads %}
  <!-- ad block -->
{% endif %}
```

```django
{% if request|should_show_ads %}
  <!-- ad block -->
{% endif %}
```

If you use tags/filters, the context processor is optional.

Python (custom placement logic):

```python
from ads_throttle.throttling import should_show_ads

if should_show_ads(request, scope="/landing/"):
    ...
```

Use `scope` to group multiple URLs under a single rule (for example, a landing
page and its variations).

## How a viewer is identified

`should_show_ads` builds a viewer fingerprint from:

- user id (`user:<id>`) or session id (`session:<key>`),
- IP address,
- User-Agent.

The fingerprint is hashed and used as a cache key.

## Settings

Settings are read from `SiteSetting` (if it exists) or from `settings.py`.

| Setting                                 | Meaning                                                                    | Default  |
| --------------------------------------- | -------------------------------------------------------------------------- | -------- |
| `ADS_VIEW_REPEAT_WINDOW_SECONDS`      | time window for counting impressions (seconds)                             | `600`  |
| `ADS_VIEW_REPEAT_THRESHOLD`           | max impressions allowed within the window                                  | `20`   |
| `ADS_BLOCK_SECONDS`                   | how long to block after the threshold is reached (seconds)                 | `3600` |
| `ADS_THROTTLE_EVENT_RECORD_SECONDS`   | how often to update block counters for a single viewer/page pair (seconds) | `60`   |
| `ADS_THROTTLE_SETTINGS_CACHE_SECONDS` | cache TTL for settings (seconds)                                           | `300`  |
| `ADS_THROTTLE_OVERRIDE_CACHE_SECONDS` | cache TTL for override decisions (seconds)                                 | `60`   |
| `ADS_THROTTLE_IP_HEADER`              | custom header name with client IP (useful behind proxies)                  | empty    |

`ADS_THROTTLE_IP_HEADER` is useful when your proxy places the real client IP in a
custom header (e.g., `X-Real-IP` or `X-Forwarded-For`). The app will read that
header instead of `REMOTE_ADDR`.

## Admin

### Ads throttle settings

Single global settings row (only one record can be created).

- **View window (seconds)** — time window for counting impressions.
- **View threshold** — max impressions within the window before blocking.
- **Block duration (seconds)** — how long to block after the threshold.
- **Event record interval (seconds)** — how often to update block counters for a single viewer/page pair.
- **Updated at** — last update timestamp.

### Ads throttle overrides

Manual overrides in admin:

- **Scope** — page path (`/courses/abc/`) or empty for site-wide.
- **Apply to** — who the rule applies to:
  - `Apply to user` — a user or `viewer_id`.
  - `Apply to IP` — a raw IP (hashed into `IP address hash`).
  - `Apply to all in scope` — everyone in the scope.
- **Action** — `Show` or `Block`.
- **User** — user record (if rule is for user).
- **Viewer ID** — `user:<id>` or `session:<key>`.
- **Raw IP address** — raw IP used to calculate the hash.
- **IP address hash** — SHA256 hash of the IP (read-only). Raw IP values are not stored.
- **Expires at** — when the rule stops being active.
- **Created at / Updated at** — record metadata.

Priority:

1. Any `Force block` rule.
2. Any `Force show` rule (if no block rule exists).
3. Default throttling logic.

### Ads throttle events

Block event log:

- **Scope** — page path.
- **Viewer hash** — hashed viewer fingerprint.
- **IP address hash** — SHA256 hash of IP.
- **First seen / Last seen** — first/last event time.
- **Count** — number of events recorded.
- **Blocked** — whether the view was blocked.

## Localization

The app supports English (default) and Russian. Admin language follows Django’s
active locale (`LANGUAGE_CODE` and `LocaleMiddleware`, or
`translation.activate(...)`).

If `LANGUAGE_CODE = "ru"` but the admin still shows English:

- Ensure `USE_I18N = True`.
- Ensure `LocaleMiddleware` is enabled and ordered correctly.
- For editable installs, compile translations: `django-admin compilemessages`.

## Caching

- View counters and block flags are stored in cache.
- Override decisions are cached separately.
- Settings are cached for `ADS_THROTTLE_SETTINGS_CACHE_SECONDS`.

## Security & performance

- IP addresses are stored only as SHA256 hashes.
- Viewer fingerprints are not stored in clear text.
- Event recording frequency is throttled by
  `ADS_THROTTLE_EVENT_RECORD_SECONDS`.

## Troubleshooting

- Ensure your cache backend supports `add` and `incr`.
- Ensure sessions are enabled (session key is used when the user is anonymous).
- For proxies/load balancers, set `ADS_THROTTLE_IP_HEADER` or provide proper
  `X-Forwarded-For`/`X-Real-IP` headers.

## Russian documentation

See [documentation.ru.md](documentation.ru.md).
