"""
ASGI config for delta_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django
django.setup()

from channels.auth import AuthMiddlewareStack 
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.urls import path
from authenticate.consumers.watchlist import WatchlistConsumer


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'delta_backend.settings')
application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    "websocket": 
        AuthMiddlewareStack(
            URLRouter([
              path('ws/watchlist/',  WatchlistConsumer.as_asgi()),
            ])
        
    ),
    
})
