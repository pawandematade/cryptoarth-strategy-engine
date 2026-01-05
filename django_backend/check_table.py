import mysql.connector
import os

# Read database config from settings
import sys
sys.path.insert(0, '/var/www/cryptoarth/django_backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'apps.delta_backend.settings'

import django
django.setup()

from django.conf import settings

db_config = settings.DATABASES['default']

# Connect to MySQL
conn = mysql.connector.connect(
    host=db_config['HOST'],
    user=db_config['USER'],
    password=db_config['PASSWORD'],
    database=db_config['NAME']
)

cursor = conn.cursor()
cursor.execute("DESCRIBE authenticate_user")
columns = cursor.fetchall()

print("authenticate_user table structure:")
print("=" * 50)
for col in columns:
    print(f"{col[0]:20} {col[1]:20} {col[2]:10} {col[3]:10} {col[4]:10}")

cursor.close()
conn.close()
