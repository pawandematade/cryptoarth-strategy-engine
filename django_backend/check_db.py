import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'apps.delta_backend.settings'
import django
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("DESCRIBE authenticate_user")
    columns = cursor.fetchall()
    print("authenticate_user table columns:")
    for col in columns:
        print(f"  {col[0]} - {col[1]}")
