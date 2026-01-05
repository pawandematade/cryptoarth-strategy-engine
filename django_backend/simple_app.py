from django.http import JsonResponse
from django.conf import settings
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "delta_backend.settings")

if not settings.configured:
    from django.conf import settings as django_settings
    django_settings.configure(
        DEBUG=True,
        ALLOWED_HOSTS=['*'],
        SECRET_KEY='temporary-key',
        INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes'],
        ROOT_URLCONF='django_backend.apps.delta_backend.urls',
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'tradearth_db',
                'USER': 'cryptoarth',
                'PASSWORD': 'cryptoarth2025',
                'HOST': 'cryptoarth-mysql.cv0ao6ygare7.ap-south-1.rds.amazonaws.com',
                'PORT': '3306',
            }
        }
    )

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

def simple_view(request):
    return JsonResponse({"status": "ok", "service": "CryptoArth API"})
