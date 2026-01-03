"""
Date utility functions for read-only APIs
Matches cryptoarth_backend/authenticate/utils/functions.py date conversion logic
"""
from datetime import datetime, time
import pytz
from typing import Tuple


def get_todays_dates() -> Tuple[datetime, datetime]:
    """
    Get start and end of today in Asia/Kolkata timezone, converted to UTC.
    Matches cryptoarth_backend/authenticate/utils/functions.py get_todays_dates()
    
    Returns:
        Tuple[datetime, datetime]: (start_of_day_utc, end_of_day_utc)
    """
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    now_kolkata = datetime.now(kolkata_tz)

    # Get start and end of today in Kolkata timezone
    start_of_day_kolkata = kolkata_tz.localize(
        datetime.combine(now_kolkata.date(), time.min)
    )
    end_of_day_kolkata = kolkata_tz.localize(
        datetime.combine(now_kolkata.date(), time.max)
    )

    # Convert to UTC for database query
    start_of_day_utc = start_of_day_kolkata.astimezone(pytz.UTC)
    end_of_day_utc = end_of_day_kolkata.astimezone(pytz.UTC)
    return start_of_day_utc, end_of_day_utc


def convert_date_range_to_utc(start_date_str: str, end_date_str: str) -> Tuple[datetime, datetime]:
    """
    Convert a given start and end date (YYYY-MM-DD) from Asia/Kolkata timezone to UTC.
    Matches cryptoarth_backend/authenticate/utils/functions.py convert_date_range_to_utc()
    
    Args:
        start_date_str: Start date in 'YYYY-MM-DD' format
        end_date_str: End date in 'YYYY-MM-DD' format
    
    Returns:
        Tuple[datetime, datetime]: (start_of_day_utc, end_of_day_utc)
    """
    kolkata_tz = pytz.timezone('Asia/Kolkata')

    # Parse input strings to date objects
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # Localize start and end times in Kolkata timezone
    start_of_day_kolkata = kolkata_tz.localize(datetime.combine(start_date, time.min))
    end_of_day_kolkata = kolkata_tz.localize(datetime.combine(end_date, time.max))

    # Convert both to UTC
    start_of_day_utc = start_of_day_kolkata.astimezone(pytz.UTC)
    end_of_day_utc = end_of_day_kolkata.astimezone(pytz.UTC)

    return start_of_day_utc, end_of_day_utc

