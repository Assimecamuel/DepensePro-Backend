
import os
from pathlib import Path

# ============================================================
# BASE DIRECTORY AND ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in (
        "true", "1", "yes", "on"
    )


def env_list(name, default=""):
    return [
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-before-deployment"
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1,192.168.100.132"
)

if not DEBUG:
    if SECRET_KEY == "dev-only-insecure-key-change-before-deployment":
        raise RuntimeError(
            "DJANGO_SECRET_KEY doit être défini en production."
        )

    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError(
            "DJANGO_ALLOWED_HOSTS doit contenir des domaines explicites."
        )


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # REST API
    "rest_framework",
    "rest_framework.authtoken",

    # CORS
    "corsheaders",

    # Main application
    "expenses",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ============================================================
# DATABASE CONFIGURATION
# SQLITE LOCAL / POSTGRESQL PRODUCTION
# ============================================================

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

if DB_ENGINE in ("postgres", "postgresql"):

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "depensepro"),
            "USER": os.getenv("DB_USER", "depensepro"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(
                os.getenv("DB_CONN_MAX_AGE", "60")
            ),
        }
    }

else:

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": int(
                os.getenv("PASSWORD_MIN_LENGTH", "8")
            ),
        },
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "Africa/Douala"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC AND MEDIA FILES
# ============================================================

STATIC_URL = "static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"

MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),

    "PAGE_SIZE": 100,

    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],

    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_RATE", "100/hour"),
        "user": os.getenv("API_USER_RATE", "1000/hour"),
    },
}


# ============================================================
# CORS CONFIGURATION
# ============================================================

CORS_ALLOW_ALL_ORIGINS = (
    DEBUG and env_bool("CORS_ALLOW_ALL_ORIGINS", False)
)

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS"
)

default_cors_regexes = ";".join([
    r"^https?://localhost(:\d+)?$",
    r"^https?://127\.0\.0\.1(:\d+)?$",
    r"^https?://192\.168\.100\.132(:\d+)?$",
])

CORS_ALLOWED_ORIGIN_REGEXES = [
    item.strip()
    for item in os.getenv(
        "CORS_ALLOWED_ORIGIN_REGEXES",
        default_cors_regexes if DEBUG else ""
    ).split(";")
    if item.strip()
]


# ============================================================
# CSRF CONFIGURATION
# ============================================================

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS"
)


# ============================================================
# EMAIL / SMTP CONFIGURATION
# ============================================================

EMAIL_HOST = os.getenv(
    "EMAIL_HOST",
    "smtp.gmail.com"
)

EMAIL_PORT = int(
    os.getenv("EMAIL_PORT", "587")
)

EMAIL_USE_TLS = env_bool(
    "EMAIL_USE_TLS",
    True
)

EMAIL_USE_SSL = env_bool(
    "EMAIL_USE_SSL",
    False
)

EMAIL_HOST_USER = os.getenv(
    "EMAIL_HOST_USER",
    ""
)

EMAIL_HOST_PASSWORD = os.getenv(
    "EMAIL_HOST_PASSWORD",
    ""
)

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@depensepro.local"
)

EMAIL_TIMEOUT = int(
    os.getenv("EMAIL_TIMEOUT", "30")
)

# SSL et TLS ne doivent pas être actifs simultanément.
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError(
        "EMAIL_USE_TLS et EMAIL_USE_SSL ne peuvent pas être "
        "activés simultanément."
    )

SMTP_CREDENTIALS_CONFIGURED = bool(
    EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
)

DEFAULT_EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if SMTP_CREDENTIALS_CONFIGURED
    else (
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    )
)

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    DEFAULT_EMAIL_BACKEND
)

# En production, ne jamais démarrer avec des identifiants SMTP absents.
if not DEBUG and not SMTP_CREDENTIALS_CONFIGURED:
    raise RuntimeError(
        "EMAIL_HOST_USER et EMAIL_HOST_PASSWORD sont obligatoires "
        "en production."
    )


# ============================================================
# PASSWORD RESET / OTP CONFIGURATION
# ============================================================

PASSWORD_RESET_OTP_EXPIRY = int(
    os.getenv("PASSWORD_RESET_OTP_EXPIRY", "600")
)

PASSWORD_RESET_MAX_ATTEMPTS = int(
    os.getenv("PASSWORD_RESET_MAX_ATTEMPTS", "5")
)

PASSWORD_RESET_RESEND_DELAY = int(
    os.getenv("PASSWORD_RESET_RESEND_DELAY", "60")
)

# Durée de validité du jeton Django standard de réinitialisation.
PASSWORD_RESET_TIMEOUT = int(
    os.getenv("PASSWORD_RESET_TIMEOUT", "900")
)


# ============================================================
# SECURITY SETTINGS - PRODUCTION
# ============================================================

if not DEBUG:

    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https"
    )

    SECURE_SSL_REDIRECT = env_bool(
        "DJANGO_SECURE_SSL_REDIRECT",
        True
    )

    SESSION_COOKIE_SECURE = True

    CSRF_COOKIE_SECURE = True

    SECURE_CONTENT_TYPE_NOSNIFF = True

    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

    X_FRAME_OPTIONS = "DENY"

    SECURE_HSTS_SECONDS = int(
        os.getenv("SECURE_HSTS_SECONDS", "31536000")
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        True
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "SECURE_HSTS_PRELOAD",
        False
    )


# ============================================================
# LOGGING
# ============================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{levelname} {asctime} {name} {message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": True,
        },
        "expenses": {
            "handlers": ["console"],
            "level": os.getenv("APP_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
