# ads_throttle — Django ad impression throttling to reduce ad network ban risk

`ads_throttle` is a Django application that limits how often ads are shown to the same viewer within a configurable time window and allows manual overrides via the Django admin interface.

It is designed to reduce the risk of ad network bans caused by abnormal or suspicious ad impression patterns (for example, bot traffic or third-party abuse).

## How it works

1. A **viewer fingerprint** is computed using:

   - authenticated user ID or session key,
   - IP address,
   - User-Agent.
2. For each page (or logical page group called a *scope*), an impression counter is stored in cache.
3. If the number of impressions exceeds the configured threshold within the time window, ads are **temporarily blocked** for that viewer.
4. Ads are automatically unblocked after the configured TTL.
5. Administrators can **force show or force block ads** for specific users, IPs, viewer IDs, or page scopes via Django Admin.

Ads are throttled — **users and traffic are not blocked**.

## Installation

```bash
pip install ads-throttle
```

Add the app to Django:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "ads_throttle",
]
```

### Optional: global context processor

Use this option **when ads are rendered on most pages**:

```python
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

### Templates (with context processor)

Best when ads appear on most pages:

```django
{% if show_ads %}
  <!-- ad block -->
{% endif %}
```

### Templates (without context processor)

Recommended when ads appear only on some pages:

```django
{% load ads_throttle_tags %}
{% show_ads as show_ads %}
{% if show_ads %}
  <!-- ad block -->
{% endif %}
```

Or:

```django
{% if request|should_show_ads %}
  <!-- ad block -->
{% endif %}
```

When using template tags or filters, the context processor is not required.

### Python (custom placement logic)

```python
from ads_throttle.throttling import should_show_ads

if should_show_ads(request, scope="/landing/"):
    ...
```

`scope` allows multiple URLs (for example, a landing page and its variants) to share the same throttling rules.

## Requirements

* Django database (PostgreSQL, MySQL, SQLite for development).
* Cache backend supporting `add` and `incr`:

  * Redis (recommended),
  * Memcached,
  * Django database cache (development only).

## Security and privacy

* IP addresses are stored only as SHA256 hashes.
* Viewer fingerprints are never stored in raw form.
* No external tracking or third-party services are used.

## What this package is NOT

* It is not an ad fraud detection system.
* It does not analyze clicks or conversions.
* It does not attempt to bypass ad network policies.

It is a **preventive throttling mechanism** that limits ad impressions
before abnormal patterns escalate into enforcement actions.

## Links

* Source code: [https://github.com/frollow/throttle](https://github.com/frollow/throttle)
* Documentation: [https://github.com/frollow/throttle/tree/master/docs](https://github.com/frollow/throttle/tree/master/docs)
