import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "realtime_chat.settings")
from django.core.asgi import get_asgi_application
django_asgi = get_asgi_application()  # must initialise Django before importing consumers
from channels.routing import ProtocolTypeRouter, URLRouter
from chat.middleware import JWTAuthMiddleware
import chat.routing

application = ProtocolTypeRouter({
    "http": django_asgi,
    "websocket": JWTAuthMiddleware(URLRouter(chat.routing.websocket_urlpatterns)),
})
