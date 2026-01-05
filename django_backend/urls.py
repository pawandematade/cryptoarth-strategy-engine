from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home(request):
    return JsonResponse({"status": "ok", "service": "CryptoArth API"})

def health_check(request):
    return JsonResponse({"status": "healthy"}, status=200)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('health/', health_check, name='health_check'),
    path('auth/', include('apps.delta_backend.auth_app.urls')),
]
