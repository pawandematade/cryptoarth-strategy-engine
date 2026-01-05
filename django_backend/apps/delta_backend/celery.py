


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
    }
    # 'check_all_position': {
    #     'task': 'delta_backend.celery.check_all_position',
    #     'schedule': crontab(minute='*/2'),  # Every 2 minutes
    # },
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
def check_all_position():
    from django_backend.apps.auth.models import Position
    from concurrent.futures import ThreadPoolExecutor, wait
    from django.db import connection
    
    userdata = Position.objects.all()
    futures = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        futures = [executor.submit(process_position, user) for user in userdata]
        
        # Wait for ALL tasks to complete
        wait(futures)
    
    # CRITICAL: Close Django database connections
    connection.close()

def get_open_position1(positions, symbol):
        """
        Returns the open quantity for a given trading symbol.
        If no active position, returns 0.
        """
        if not positions:  # handles [] or None
            return 0
        
        for pos in positions:
            if pos.get('pair') == symbol:
                return pos.get('active_pos', 0)  # return active position size
        
        return 0

def convert_symbol(symbol):
    # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
    base_currency = symbol.replace('_USDT', 'USD')
    base_currency1 = base_currency.replace('B-', '')
    return base_currency1

def process_position(user):
    from django_backend.apps.auth.utils.coindcx import coindcxclient
    from django_backend.apps.auth.models import OrderDetails,tradeDetails
    from django_backend.apps.auth.utils.functions import get_live_price
    from django_backend.apps.auth.utils.deltaexchange import DeltaExchangeClient
    from django.db import connection
    
    apikey,apisecret = user.broker.get_api_credentials()
    if user.side == "buy":
        side12 = "sell"
    else:
        side12 = "buy"
    if user.broker.broker == "Coindcx":
        client = coindcxclient(api_key=apikey, api_secret=apisecret)
        position = client.get_positions_coindcx(symbol=user.symbol)
        quantity_balance = get_open_position1(position, user.symbol)
        user_qty = float(user.quantity)
        if user.side == "buy" and quantity_balance > 0:
            pass
        else:
            symbol = convert_symbol(user.symbol)
            price = get_live_price(symbol)

            margin_used = float(price) * float(user_qty) 
            post = OrderDetails(owner_id = user.owner.id,orderid = user.order_id,symbol = user.symbol,side = user.side,stratergy = user.stratergy,buyprice = user.price,sellprice = float(price),buyquantity = user.quantity,sellquantity = user_qty,status = "Completed",profit = ((user_qty * float(price)) - (float(user.quantity) * float(user.price))),stratergy_name =user.stratergy_name,broker_id = user.broker.id )
            post.save()
            post1 = tradeDetails(owner_id = user.owner.id,symbol = user.symbol,price =float(price),quantity = user_qty,side = side12,unique = user.order_id ,status ="Completed",orderid = user.order_id,stratergy = user.stratergy,remark="Order Already closed at broker end.", stratergy_name = user.stratergy_name,margin = margin_used,broker_id = user.broker.id)
            post1.save()
            user.delete()
        if user.side == "sell" and quantity_balance < 0:
            pass
        else:
            symbol = convert_symbol(user.symbol)
            price = get_live_price(symbol)

            margin_used = float(price) * float(user_qty) 
            post = OrderDetails(owner_id = user.owner.id,orderid = user.order_id,symbol = user.symbol,side = user.side,stratergy = user.stratergy,sellprice = user.price,buyprice = float(price),sellquantity = user.quantity,buyquantity = user_qty,status = "Completed",profit = ((float(user.quantity) * float(user.price)) - (user_qty * float(price))),stratergy_name =user.stratergy_name,broker_id = user.broker.id )
            post.save()
            post1 = tradeDetails(owner_id = user.owner.id,symbol = user.symbol,price =float(price),quantity = user_qty,side = side12,unique = user.order_id ,status ="Completed",orderid = user.order_id,stratergy = user.stratergy,remark="Order Already closed at broker end.", stratergy_name = user.stratergy_name,margin = margin_used,broker_id = user.broker.id)
            post1.save()
            user.delete()
    else:
        client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
        position = client.get_positions(product_id=user.symbol)
        if position['success'] == True:
            quantity_balance = int(position['result']['size'])
            user_qty = int(float(user.quantity))
            

            if user.side == "buy" and quantity_balance > 0:
                pass
            else:
                
                price = get_live_price(user.symbol)

                margin_used = float(price) * float(user_qty) 
                post = OrderDetails(owner_id = user.owner.id,orderid = user.order_id,symbol = user.symbol,side = user.side,stratergy = user.stratergy,buyprice = user.price,sellprice = float(price),buyquantity = user.quantity,sellquantity = user_qty,status = "Completed",profit = ((user_qty * float(price)) - (float(user.quantity) * float(user.price))),stratergy_name =user.stratergy_name,broker_id = user.broker.id )
                post.save()
                post1 = tradeDetails(owner_id = user.owner.id,symbol = user.symbol,price =float(price),quantity = user_qty,side = side12,unique = user.order_id ,status ="Completed",orderid = user.order_id,stratergy = user.stratergy,remark="Order Already closed at broker end.", stratergy_name = user.stratergy_name,margin = margin_used,broker_id = user.broker.id)
                post1.save()
                user.delete()
            if user.side == "sell" and quantity_balance < 0:
                pass
            else:
                price = get_live_price(user.symbol)

                margin_used = float(price) * float(user_qty) 
                post = OrderDetails(owner_id = user.owner.id,orderid = user.order_id,symbol = user.symbol,side = user.side,stratergy = user.stratergy,sellprice = user.price,buyprice = float(price),sellquantity = user.quantity,buyquantity = user_qty,status = "Completed",profit = ((float(user.quantity) * float(user.price)) - (user_qty * float(price))),stratergy_name =user.stratergy_name,broker_id = user.broker.id )
                post.save()
                post1 = tradeDetails(owner_id = user.owner.id,symbol = user.symbol,price =float(price),quantity = user_qty,side = side12,unique = user.order_id ,status ="Completed",orderid = user.order_id,stratergy = user.stratergy,remark="Order Already closed at broker end.", stratergy_name = user.stratergy_name,margin = margin_used,broker_id = user.broker.id)
                post1.save()
                user.delete()
    


   

@shared_task
def check_copy_tp():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor

    # copysignal.objects.filter(status = "Active", side = "BUY").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Active", side = "buy")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_tp12,token)for token in tokens_set]


@shared_task
def check_copy_sell_tp():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor

    # copysignal.objects.filter(status = "Active", side = "SELL").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Active", side = "sell")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_sell_tp23,token)for token in tokens_set]


@shared_task
def check_copy_limit():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    # copysignal.objects.filter(status = "Pending", side = "BUY", typeq = "limit").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Pending", side = "buy", typeq = "limit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit,token)for token in tokens_set]


@shared_task
def check_copy_limit1():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    # copysignal.objects.filter(status = "Pending", side = "BUY", typeq = "limit").update(status = "Processing")
    userdata = copysignal.objects.filter(status = "Pending", side = "buy", typeq = "sllimit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit1,token)for token in tokens_set]


@shared_task
def check_copy_sell_limit():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    userdata = copysignal.objects.filter(status = "Pending", side = "sell", typeq = "limit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit,token)for token in tokens_set]


@shared_task
def check_copy_sell_limit1():
    from django_backend.apps.auth.models import copysignal
    from concurrent.futures import ThreadPoolExecutor
    userdata = copysignal.objects.filter(status = "Pending", side = "sell", typeq = "sllimit")
    tokens_set = set(userdata.values_list("symbol", flat=True))
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit1,token)for token in tokens_set]









def process_token_tp12(token):
    from django.core.cache import cache
    from django.db.models import Q,F
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
    price =  float(get_live_price(token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "buy") & (Q(target__lt=price) | Q(stoploss__gt=price)) & Q(symbol = token)).update(status = "Processing")

    userdata_set = copysignal.objects.filter(Q(status = "Processing") &  Q(side = "buy") & (Q(target__lt=price) | Q(stoploss__gt=price)) & Q(symbol = token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "buy") & Q(trailingprice__lt = price) & Q(target__gt =price ) & Q(is_trailing = True)).update(stoploss=F('stoploss') + F('trailingpoints'),trailingprice=F('trailingprice')+F('trailingpoints'))
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task,signal)for signal in userdata_set]



def process_token_sell_tp23(token):
   
    from django.core.cache import cache
    from django.db.models import Q,F
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
    price =  float(get_live_price(token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "sell") & (Q(target__gt=price) | Q(stoploss__lt=price)) & Q(symbol = token)).update(status = "Processing")

    userdata_set = copysignal.objects.filter(Q(status = "Processing") &  Q(side = "sell") & (Q(target__gt=price) | Q(stoploss__lt=price)) & Q(symbol = token))

    copysignal.objects.filter(Q(status = "Active") &  Q(side = "sell") & Q(trailingprice__gt = price) & Q(target__lt =price ) & Q(is_trailing = True)).update(stoploss=F('stoploss') - F('trailingpoints'),trailingprice=F('trailingprice') - F('trailingpoints'))
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task,signal)for signal in userdata_set]


def process_buy_limit(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "buy", typeq = "limit",symbol = token,entry__gt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "buy", typeq = "limit",symbol = token,entry__gt =price)

    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]


def process_buy_limit1(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "buy", typeq = "sllimit",symbol = token,entry__lt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "buy", typeq = "sllimit",symbol = token,entry__lt =price)
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]

def process_sell_limit(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
    price =  float(get_live_price(token))
    copysignal.objects.filter(status = "Pending", side = "sell", typeq = "limit",symbol = token , entry__lt =price).update(status = "Processing")
    userdata_set = copysignal.objects.filter(status = "Processing", side = "sell", typeq = "limit",symbol = token , entry__lt =price)

    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1,signal)for signal in userdata_set]


def process_sell_limit1(token):
    from django.core.cache import cache
    from concurrent.futures import ThreadPoolExecutor
    from django_backend.apps.auth.models import copysignal
    from django_backend.apps.auth.utils.functions import get_live_price
    
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
        


