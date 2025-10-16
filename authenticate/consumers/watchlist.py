from channels.generic.websocket import AsyncWebsocketConsumer

from channels.db import database_sync_to_async
from django.conf import settings
from authenticate.models import User
from asgiref.sync import async_to_sync

from channels.db import database_sync_to_async
from authenticate.models import SymbolMaster
from authenticate.serializers import SymbolMasterSerializer


from django.core.cache import cache


import jwt
import json
import asyncio

class WatchlistConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        temp = self.scope['query_string'].decode()
        
        authorization = temp.split("=")
        user = await self.authenticate(authorization[1])
        if user is not None:
            self.scope['user'] = user
            
        else:
            await self.close()

    async def disconnect(self, close_code):
        pass

    
    async def receive(self, text_data):
        text_data = json.loads(text_data)

        symbol = text_data['symbol']
        cache_key = f"watchlist_data_{symbol}"
        data = cache.get(cache_key)
        if not data:
            userdata = SymbolMaster.objects.all()
            if symbol != "NA":
            
                parts = symbol.split()
                for part in parts:
                    userdata = userdata.filter(symbol__icontains=part)
                userdata =userdata[:20]
            else:
                userdata = userdata[:20]
            data = await self.getdata(userdata)
            cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
            await self.send_response(data)
        else:
            await self.send_response(data)

    @database_sync_to_async
    def getdata(self,userdata):
        serializer = SymbolMasterSerializer(userdata,many=True)
        data = serializer.data
        return data

    async def send_response(self, response_data):
        await self.send(text_data=json.dumps(response_data))
        
    
    async def authenticate(self,headers):
        # Extract the authentication token from the request headers
        try:
            token = headers
            try:
                decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                user_id = decoded_token['user_id']
                user = await self.get_user(user_id)
                return (user)
            except (jwt.exceptions.DecodeError, User.DoesNotExist):
                pass
        except KeyError:
            pass

    @database_sync_to_async
    def get_user(self, user_id):
        cache_key = f"user_profile_{user_id}"
        data = cache.get(cache_key)
        if not data:
            user = User.objects.get(id=user_id)
            
            return user
        return data