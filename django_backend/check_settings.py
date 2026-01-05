import sys
sys.path.insert(0, '.')
try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'delta_backend.settings')
    import django
    django.setup()
    from django.conf import settings
    print("✓ Django settings loaded successfully")
    print(f"INSTALLED_APPS: {settings.INSTALLED_APPS}")
except Exception as e:
    print(f"✗ Error: {e}")
