from django.apps import AppConfig

class AuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auth'  # or something like this
    label = 'crypto_auth_app'  # might have label
