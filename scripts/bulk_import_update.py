# Bulk import update
import os, re

patterns = [
    (r"from app\.database import", "from common.db import"),
    (r"from app\.store\.redis_client import", "from common.redis import"),
    (r"from order\.auth\.credentials import (set_api_credentials|get_api_credentials)", r"from common.security import set_broker_credentials as \1, get_broker_credentials"),
    (r"from order\.broker\.delta import", "from order.brokers.delta.client import"),
    (r"from order\.broker\.coindcx import", "from order.brokers.coindcx.client import"),
    (r"from order\.orders\.functions import", "from order.orders.service import"),
    (r"from order\.positions\.position_sync import", "from order.positions.service import"),
    (r"from app\.api\.user_dependencies import get_current_user", "from common.auth import get_current_user"),
]

# This is a reference - actual updates done via search_replace
