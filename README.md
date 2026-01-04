# ads_throttle — Django ad impression throttling to reduce ad network ban risk

`ads_throttle` is a Django application that limits how often ads are shown to the same viewer within a configurable time window and allows administrators to override
decisions via the Django admin interface.

The primary goal is to reduce the risk of **ad network bans** caused by abnormal or suspicious ad impression patterns (for example, bot traffic or third-party abuse), without blocking users or traffic.

## How it works

1. A **viewer fingerprint** is computed using:

   - authenticated user ID or session key,
   - IP address,
   - User-Agent.
2. A per-page (or logical page group called a *scope*) impression counter is stored in cache.
3. When the impression threshold is exceeded within the configured time window, ads are **temporarily blocked** for that viewer.
4. Ads are automatically unblocked after the configured TTL.
5. Administrators can **force show or force block ads** for specific users, IPs, viewer IDs, or scopes via Django Admin.

Ads are throttled — **users and traffic are never blocked**.

## Installation

```bash
pip install ads-throttle
```

Add the app and (optionally) the context processor:

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

The context processor is recommended when ads are rendered on most pages.

## Usage

### Templates (with context processor)

Best when ads are shown on most pages:

```django
{% if show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

### Templates (without context processor)

Recommended when ads appear only on selected pages:

```django
{% load ads_throttle_tags %}
{% show_ads as show_ads %}
{% if show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

Or using a filter:

```django
{% if request|should_show_ads %}
  {# ... your ad block ... #}
{% endif %}
```

When using tags or filters, the context processor can be omitted to avoid running checks on pages without ads.

### Python (custom placement logic)

```python
from ads_throttle.throttling import should_show_ads

if should_show_ads(request, scope="/landing/"):
    ...
```

`scope` allows multiple URLs (for example, a landing page and its variants) to share the same throttling rules.

## Settings

Settings can be defined in `settings.py` or via the **Ads throttle settings**
record in Django Admin (admin values take precedence).

* `ADS_VIEW_REPEAT_WINDOW_SECONDS` — impression counting window (seconds)
* `ADS_VIEW_REPEAT_THRESHOLD` — max impressions within the window
* `ADS_BLOCK_SECONDS` — block duration after threshold is reached
* `ADS_THROTTLE_EVENT_RECORD_SECONDS` — event recording interval
* `ADS_THROTTLE_SETTINGS_CACHE_SECONDS` — settings cache TTL
* `ADS_THROTTLE_OVERRIDE_CACHE_SECONDS` — override cache TTL
* `ADS_THROTTLE_IP_HEADER` — header containing real client IP (optional)

## Admin models

### Ads throttle settings

Single global record with throttling parameters:

* **View window (seconds)**
* **View threshold**
* **Block duration (seconds)**
* **Event record interval (seconds)**

### Ads throttle overrides

Manual override rules:

* **Scope** — page path (`/courses/abc/`) or empty for site-wide
* **Apply to** — user, IP, or all viewers in scope
* **Action** — show or block
* **User**
* **Viewer ID** — `user:<id>` or `session:<key>`
* **Raw IP address** — used to compute hash
* **IP address hash** — SHA256 (raw IP is not stored)
* **Expires at**

### Ads throttle events

Block event log:

* **Scope**
* **Viewer hash**
* **IP address hash**
* **First seen / Last seen**
* **Count**
* **Blocked**

## Security and privacy

* IP addresses are stored only as SHA256 hashes.
* Viewer fingerprints are never stored in raw form.
* No external tracking or third-party services are used.

## What this package is NOT

* It is not an ad fraud detection system.
* It does not analyze clicks or conversions.
* It does not attempt to bypass ad network policies.

It is a **preventive throttling mechanism** that limits ad impressions before
abnormal patterns escalate into enforcement actions.

## Background and real-world context

* [How ad impression fraud can get your Django site banned — even if it’s not your fault](https://medium.com/@arfr/how-ad-impression-fraud-can-get-your-django-site-banned-even-if-its-not-your-fault-cdd1da23564a)

## Package

**PyPI:** [https://pypi.org/project/ads-throttle](https://pypi.org/project/ads-throttle)

## Documentation

Full documentation is available in the [/docs](https://github.com/frollow/throttle/tree/master/docs) directory.
