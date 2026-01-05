from pathlib import Path
import os
from decouple import Config, RepositoryEnv
import os

# Load environment variables from .env.production explicitly
env_path = '/var/www/cryptoarth/.env.production'
config = Config(RepositoryEnv(env_path))

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config('SECRET_KEY', default='cryptoarth-jwt-secret-2025-production-final')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = ['*']
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','corsheaders']

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "https://trade-panel.cryptoarth.in",
    "https://trade-api.cryptoarth.in",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True  # Important for sending cookies
CORS_ALLOW_ALL_ORIGINS = False  # Better to be specific

MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware','django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'apps.delta_backend.urls'
WSGI_APPLICATION = 'apps.delta_backend.wsgi.application'
DATABASES = {'default':{'ENGINE':'django.db.backends.mysql','NAME':'tradearth_db','USER':'cryptoarth','PASSWORD':'cryptoarth2025','HOST':'cryptoarth-mysql.cv0ao6ygare7.ap-south-1.rds.amazonaws.com','PORT':'3306','OPTIONS':{'charset':'utf8mb4'}}}
DATABASES = {'default':{'ENGINE':'django.db.backends.mysql','NAME':'tradearth_db','USER':'cryptoarth','PASSWORD':'cryptoarth2025','HOST':'cryptoarth-mysql.cv0ao6ygare7.ap-south-1.rds.amazonaws.com','PORT':'3306','OPTIONS':{'charset':'utf8mb4'}}}

# Redis Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://cryptoarth-redis-prod.cj4aex.ng.0001.aps1.cache.amazonaws.com:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'CONNECTION_POOL_KWARGS': {'max_connections': 100},
            'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
        },
        'KEY_PREFIX': 'django_'
    }
}

# Session cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.debug','django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
CSRF_TRUSTED_ORIGINS = ['https://trade-api.cryptoarth.in','https://cryptoarth.in']
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True


# OTP Configuration - Added by fix script
msg91_auth_key = config('msg91_auth_key', '')
msg91_flow_id = config('msg91_flow_id', '')
AISENSY_API_KEY = config('AISENSY_API_KEY', '')



# Session settings for cross-subdomain access
SESSION_COOKIE_DOMAIN = '.cryptoarth.in'  # Note the leading dot for all subdomains
SESSION_COOKIE_SECURE = True  # Use secure cookies in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'  # Or 'None' if needed for cross-site
CSRF_COOKIE_DOMAIN = '.cryptoarth.in'
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    "https://trade-panel.cryptoarth.in",
    "https://trade-api.cryptoarth.in",
    "https://cryptoarth.in"
]
