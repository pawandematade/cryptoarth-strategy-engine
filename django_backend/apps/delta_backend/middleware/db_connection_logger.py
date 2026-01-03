import logging
from django.db import connections


class DBConnectionLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Before view
        open_connections_before = sum(
            1 for conn in connections.all() if conn.connection is not None
        )
        print(f"[BEFORE] Open DB connections: {open_connections_before}")

        response = self.get_response(request)

        # After view
        open_connections_after = sum(
            1 for conn in connections.all() if conn.connection is not None
        )
        print(f"[AFTER] Open DB connections: {open_connections_after}")

        return response
