


from __future__ import absolute_import, unicode_literals
import os
from celery import Celery


# Set the default Celery settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'delta_backend.settings')

app = Celery('delta_backend')

# Load task modules from all registered Django app configs.
app.config_from_object('django.conf:settings', namespace='CELERY')
from datetime import timedelta
app.conf.enable_utc = False
app.conf.update(
    timezone = 'Asia/Kolkata',
    broker_connection_retry_on_startup=True,
    worker_heartbeat=10,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_concurrency=4,
    )
# Define the broker URL for your chosen message broker (e.g., RabbitMQ)
app.conf.broker_url = 'amqp://admin:Tradearth456s@64.227.154.37:5672'


from celery.schedules import (
    schedule,
)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'check_copy_tp': {
        'task': 'delta_backend.celery.check_copy_tp',
        'schedule': schedule(run_every=1), 
    },
    'check_copy_sell_tp': {
        'task': 'delta_backend.celery.check_copy_sell_tp',
        'schedule': schedule(run_every=1), 
    },
    'check_copy_limit': {
        'task': 'delta_backend.celery.check_copy_limit',
        'schedule': schedule(run_every=1), 
    },
    'check_copy_limit1': {
        'task': 'delta_backend.celery.check_copy_limit1',
        'schedule': schedule(run_every=1), 
    },
    'check_copy_sell_limit': {
        'task': 'delta_backend.celery.check_copy_sell_limit',
        'schedule': schedule(run_every=1), 
    },
    'check_copy_sell_limit1': {
        'task': 'delta_backend.celery.check_copy_sell_limit1',
        'schedule': schedule(run_every=1), 
    },
    # 'broker_login_deactivate': {
    #     'task': 'dematade.celery.broker_login_deactivate',
    #     'schedule': crontab(hour=23, minute=37),
    # },

    
}
# Load task modules from all registered Django app configs
app.autodiscover_tasks()




@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

from celery import shared_task
from celery import current_app



@shared_task
def check_copy_tp():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor

    # copysignal.objects.filter(status = "Active", side = "BUY").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Active", side = "buy")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_tp12,token)for token in tokens_set]


@shared_task
def check_copy_sell_tp():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor

    # copysignal.objects.filter(status = "Active", side = "SELL").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Active", side = "sell")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_sell_tp23,token)for token in tokens_set]


@shared_task
def check_copy_limit():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    # copysignal.objects.filter(status = "Pending", side = "BUY", typeq = "limit").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Pending", side = "buy", typeq = "limit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit,token)for token in tokens_set]


@shared_task
def check_copy_limit1():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    # copysignal.objects.filter(status = "Pending", side = "BUY", typeq = "limit").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Pending", side = "buy", typeq = "sllimit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit1,token)for token in tokens_set]


@shared_task
def check_copy_sell_limit():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    userdata = copysignal.objects.filter(status = "Pending", side = "sell", typeq = "limit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit,token)for token in tokens_set]


@shared_task
def check_copy_sell_limit1():
    from authenticate.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    userdata = copysignal.objects.filter(status = "Pending", side = "sell", typeq = "sllimit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit1,token)for token in tokens_set]









def process_token_tp12(token):
    from django.core.cache import cache
    from django.db.models import Q,F
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "buy") & (Q(target__lt=price) | Q(stoploss__gt=price)) & Q(symbol = token)).update(status = "Processing")

    userdata_set = copysignal.objects.filter(Q(status = "Processing") &  Q(side = "buy") & (Q(target__lt=price) | Q(stoploss__gt=price)) & Q(symbol = token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "buy") & Q(trailingprice__lt = price) & Q(target__gt =price )).update(stoploss=F('stoploss') + F('trailingpoints'),trailingprice=F('trailingprice')+F('trailingpoints'))
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task,signal)for signal in userdata_set]



def process_token_sell_tp23(token):
   
    from django.core.cache import cache
    from django.db.models import Q,F
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "sell") & (Q(target__gt=price) | Q(stoploss__lt=price)) & Q(symbol = token)).update(status = "Processing")

    userdata_set = copysignal.objects.filter(Q(status = "Processing") &  Q(side = "sell") & (Q(target__gt=price) | Q(stoploss__lt=price)) & Q(symbol = token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "sell") & Q(trailingprice__gt = price) & Q(target__lt =price )).update(stoploss=F('stoploss') - F('trailingpoints'),trailingprice=F('trailingprice') - F('trailingpoints'))
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task,signal)for signal in userdata_set]


def process_buy_limit(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "buy", typeq = "limit",symbol = token,entry__gt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "buy", typeq = "limit",symbol = token,entry__gt =price)

    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]


def process_buy_limit1(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "buy", typeq = "sllimit",symbol = token,entry__lt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "buy", typeq = "sllimit",symbol = token,entry__lt =price)
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]

def process_sell_limit(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "sell", typeq = "limit",symbol = token , entry__lt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "sell", typeq = "limit",symbol = token , entry__lt =price)

    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]


def process_sell_limit1(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from authenticate.models import copysignal
    from authenticate.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "sell", typeq = "sllimit",symbol = token , entry__gt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "sell", typeq = "sllimit",symbol = token , entry__gt =price)

    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]



def process_task(signal):
    try:
        import pytz
        from datetime import datetime
        import requests
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
        headers = {
            "Content-Type": "text/plain"
        }
        if signal.side == "buy":
            side = "sell"
        else:
            side = "buy"
        
        parts2 = [
                signal.symbol,
                str(signal.symbolid),"0","0","0",str(signal.strategy.id),str(signal.strategy.stratergy_code),"DELTA",side,formatted_datetime,str(signal.leverage),str(signal.capital),"Exit"
            ]
        final_string2 = "|".join(parts2) + "|"
        response = requests.post(signal.url, data=final_string2.encode("utf-8"), headers=headers)
        signal.status = "Completed"
        signal.save()
        
    except Exception as e:
        print(str(e))


def process_task1(signal):
    import pytz
    from datetime import datetime
    import requests
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
    headers = {
        "Content-Type": "text/plain"
    }
    
    parts2 = [
                signal.symbol,
                str(signal.symbolid),"0","0","0",str(signal.strategy.id),str(signal.strategy.stratergy_code),"DELTA",signal.side,formatted_datetime,str(signal.leverage),str(signal.capital),"Entry"
            ]
    final_string2 = "|".join(parts2) + "|"
    response = requests.post(signal.url, data=final_string2.encode("utf-8"), headers=headers)
    signal.status = "Active"
    signal.save()
        


