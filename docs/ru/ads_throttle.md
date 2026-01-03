# Документация: ads_throttle

`ads_throttle` — Django-приложение, которое ограничивает частоту показа рекламы
для одного зрителя в пределах заданного окна и позволяет вручную управлять
решением через админку.

## Сценарии использования

- Защитить страницы от чрезмерного количества рекламных показов.
- Форсировать показ/блокировку для конкретного пользователя, сессии или IP.
- Получать журнал событий блокировки для аналитики.

## Архитектура

Основные части приложения:

- **Модели** (`ads_throttle/models.py`)
  - `SiteSetting` — глобальные параметры throttling.
  - `AdsThrottleOverride` — ручные переопределения решения.
  - `AdsThrottleEvent` — журнал событий блокировки.
- **Логика throttling** (`ads_throttle/throttling.py`)
  - функция `should_show_ads` — основной вход для проверки.
- **Контекстный процессор** (`ads_throttle/context_processors.py`)
  - добавляет `show_ads` в шаблонный контекст.
- **Template-теги/фильтры** (`ads_throttle/templatetags/ads_throttle_tags.py`)
  - тег `show_ads` и фильтр `should_show_ads` для выборочного использования.
- **Админка** (`ads_throttle/admin.py`)
  - формы, правила и фильтры.

## Требования

- База данных для моделей Django (например, PostgreSQL, MySQL или SQLite для dev).
- Кэш, поддерживающий `add` и `incr` (например, Redis, Memcached или DB cache).
  Для продакшена рекомендуется Redis или Memcached.

## Установка и подключение

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

## Быстрый старт

Шаблоны (контекстный процессор — когда реклама на всех страницах):

```django
{% if show_ads %}
  <!-- рекламный блок -->
{% endif %}
```

Шаблоны (template-теги/фильтры — когда реклама только на части страниц, чтобы не выполнять проверку на каждой странице):

```django
{% load ads_throttle_tags %}
{% show_ads as show_ads %}
{% if show_ads %}
  <!-- рекламный блок -->
{% endif %}
```

```django
{% if request|should_show_ads %}
  <!-- рекламный блок -->
{% endif %}
```

Если используете теги/фильтры, контекстный процессор можно не подключать.

Python (кастомная логика размещения):

```python
from ads_throttle.throttling import should_show_ads

if should_show_ads(request, scope="/landing/"):
    ...
```

`scope` помогает объединить несколько URL под одним правилом (например,
лендинг и его вариации).

## Как определяется зритель

Функция `should_show_ads` строит отпечаток зрителя из:

- идентификатора пользователя (`user:<id>`) или сессии (`session:<key>`),
- IP адреса,
- User-Agent.

Этот отпечаток хэшируется и используется как ключ для счетчиков.

## Настройки

Настройки читаются из `SiteSetting` (если запись есть), иначе — из `settings.py`.

| Настройка                      | Значение                                                                                                                     | По умолчанию |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| `ADS_VIEW_REPEAT_WINDOW_SECONDS`      | окно времени для подсчета показов (сек.)                                                             | `600`                 |
| `ADS_VIEW_REPEAT_THRESHOLD`           | максимальное число показов в окне                                                                       | `20`                  |
| `ADS_BLOCK_SECONDS`                   | срок блокировки после достижения лимита (сек.)                                                 | `3600`                |
| `ADS_THROTTLE_EVENT_RECORD_SECONDS`   | как часто обновлять счетчики блокировки для пары зритель/страница (сек.) | `60`                  |
| `ADS_THROTTLE_SETTINGS_CACHE_SECONDS` | TTL кэша настроек (сек.)                                                                                              | `300`                 |
| `ADS_THROTTLE_OVERRIDE_CACHE_SECONDS` | TTL кэша override-решений (сек.)                                                                                       | `60`                  |
| `ADS_THROTTLE_IP_HEADER`              | имя заголовка с IP клиента (актуально за прокси)                                                | пусто              |

`ADS_THROTTLE_IP_HEADER` нужен, когда реальный IP приходит в специальном
заголовке от прокси (например, `X-Real-IP` или `X-Forwarded-For`). В этом случае
приложение берет IP из заголовка, а не из `REMOTE_ADDR`.

## Админка

### Ads throttle settings

Единственная запись (добавить можно только одну). Параметры действуют глобально.

- **View window (seconds)** — окно времени для подсчета показов.
- **View threshold** — максимальное число показов в окне до блокировки.
- **Block duration (seconds)** — срок блокировки после достижения лимита.
- **Event record interval (seconds)** — как часто обновлять счетчики блокировки для пары зритель/страница.
- **Updated at** — время последнего изменения.

### Ads throttle overrides

Ручные переопределения решения. В админке доступны вспомогательные поля:

- **Scope** — путь страницы (`/courses/abc/`) или пусто для всего сайта.
- **Apply to** — кого применить правило:
  - `Apply to user` — пользователь или `viewer_id`.
  - `Apply to IP` — IP адрес (хэшируется в `IP address hash`).
  - `Apply to all in scope` — правило для всех зрителей в данном scope.
- **Action** — решение: `Show` или `Block`.
- **User** — пользователь (если правило для user).
- **Viewer ID** — идентификатор зрителя (`user:<id>` или `session:<key>`).
- **Raw IP address** — IP, из которого рассчитывается хеш.
- **IP address hash** — SHA256 хеш IP (read-only). Исходный IP не сохраняется.
- **Expires at** — когда правило перестает действовать.
- **Created at / Updated at** — метаданные записи.

Правила приоритизируются так:

1. `Force block` (если есть хотя бы одно соответствующее правило).
2. `Force show` (если блокировки нет).
3. Обычная логика throttling.

### Ads throttle events

Журнал событий блокировки/показа.

- **Scope** — путь страницы.
- **Viewer hash** — хеш отпечатка зрителя.
- **IP address hash** — SHA256 хеш IP.
- **First seen / Last seen** — первый/последний раз в окне.
- **Count** — количество событий.
- **Blocked** — был ли показ заблокирован.

## Локализация

Приложение поддерживает английский и русский языки. Язык админки определяется
активной локалью Django (`LANGUAGE_CODE`, `LocaleMiddleware` или
`translation.activate(...)`).

Если при `LANGUAGE_CODE = "ru"` админка остаётся на английском:

- Убедитесь, что `USE_I18N = True`.
- Проверьте, что включён `LocaleMiddleware` и он стоит в правильном порядке.
- Для editable-инсталляций с исходниками выполните `django-admin compilemessages`.

## Кэширование

- Счетчики показов и блокировки хранятся в кэше.
- Решения override кешируются отдельным ключом.
- Настройки из `SiteSetting` кешируются на `ADS_THROTTLE_SETTINGS_CACHE_SECONDS`.

## Безопасность и производительность

- IP сохраняется только в виде SHA256-хеша.
- Отпечаток зрителя не хранится в открытом виде.
- Запись событий блокировки может быть ограничена настройкой
  `ADS_THROTTLE_EVENT_RECORD_SECONDS`.

## Диагностика

- Проверьте корректность кэша (поддерживает `add`, `incr`).
- Убедитесь, что `request.session.session_key` формируется, иначе используется
  cookie с `SESSION_COOKIE_NAME`.
- При проксировании установите `ADS_THROTTLE_IP_HEADER` или корректный
  `X-Forwarded-For`/`X-Real-IP`.
