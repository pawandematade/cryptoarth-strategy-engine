from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status , permissions,viewsets
from django.db import transaction, connection

from django.core.cache import cache
from .models import User,Watchlist, SymbolMaster,highLowstratergy,tradeDetails,OrderDetails,SignalMaster,Position,adminPosition,userStratergyPortfolio,copysignal
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.exceptions import APIException
from rest_framework.decorators import action
from .serializers import SendOTPSerializer,UserSignupSerializer,OTPLoginSerializer,UserSerializer,WatchlistSerializer,HighLowStrategySerializer,TradeSerializer,OrderDetailsSerializer,UserStrategyPortfolioSerializer,TradeDetailsSerializer,copySignalSerializers,HighLowStrategySerializer1,adminTradeSerializer,adminOrderDetailsSerializer,PositionSerializer

from django.db.models import Q
from .permissions import IsStaff
from django.utils import timezone



class SendOTPView(APIView):
    """
    View to send OTP via providers (e.g., Msg91 and Aisensy).
    If user doesn't exist, it creates a user.
    """

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        try:
            if serializer.is_valid(raise_exception=True):
                data = serializer.validated_data
                return Response({"message": "OTP sent successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            connection.close()


class SignupView(APIView):
    """
    View to sign up user using validated phone and send JWT tokens.
    Should be called after OTP is verified (handled in frontend).
    """
    def post(self, request):
        # Pass request data to the serializer
        serializer = UserSignupSerializer(data=request.data)

        if serializer.is_valid():
            # If valid, create the user

            result = serializer.save()

            # Prepare the response data
            response_data = {
                'message': 'User registered successfully.',
                'status': True,
                'access': result['access'],
                'refresh': result['refresh'],
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        # If serializer is not valid, return errors
        return Response({
            'message': 'User registration failed.',
            'status': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    




class OTPLoginView(APIView):
    """
    View to log in user using OTP and return JWT tokens.
    """

    def post(self, request):
        serializer = OTPLoginSerializer(data=request.data)
        try:
            if serializer.is_valid(raise_exception=True):
                data = serializer.validated_data
                return Response({
                    "message": "Login successful.",
                    "access": data["access"],
                    "refresh": data["refresh"],
                    "user_id": data["user"].id
                }, status=status.HTTP_200_OK)
        except Exception as e:
            if isinstance(e, APIException):
                # Extract details from DRF validation/auth exceptions
                detail = e.detail
                if isinstance(detail, dict):
                    message = list(detail.values())[0][0] if isinstance(list(detail.values())[0], list) else list(detail.values())[0]
                elif isinstance(detail, list):
                    message = detail[0]
                else:
                    message = str(detail)
                return Response({"message": message, "status": False}, status=e.status_code)
        finally:
            connection.close()




class PhoneCheckView(APIView):
    """
    View to check if a phone number is already registered.
    Returns True if the phone number exists, otherwise False.
    """

    def post(self, request):
        with transaction.atomic():
            phone = request.data.get('phone')
            if not phone:
                return Response({"error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

            exists = User.objects.filter(phone=phone).exists()
        return Response({"exists": exists}, status=status.HTTP_200_OK)
    

class UserByPhoneView(APIView):
    def get(self, request, phone):
        try:
            cache_key = f"admin_user_profile_{phone}"
            data = cache.get(cache_key)
            if not data:
                user = User.objects.get(phone=phone)
                serializer = UserSerializer(user)
                cache.set(cache_key, serializer.data, timeout=60 * 100)
                return Response(serializer.data)
            return Response(data)
                
        except User.DoesNotExist:
            return Response(
                {"error": "User with this phone number does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def put(self, request):
        user_id = request.data.get('user_id')
        
        # Create update dictionary with only provided fields
        update_data = {}
        
        if request.data.get('first_name'):
            update_data['first_name'] = request.data.get('first_name')
        if request.data.get('last_name'):
            update_data['last_name'] = request.data.get('last_name')
        if request.data.get('email'):
            update_data['email'] = request.data.get('email')
        if request.data.get('phone'):
            update_data['phone'] = request.data.get('phone')
        
        # Single database query
        if update_data:
            User.objects.filter(id=user_id).update(**update_data)
        
        
        return Response({"message": "User updated successfully"})



class UserDetailView(APIView):
    # Only authenticated users can access this view
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Generate a unique cache key for the current user
        cache_key = f"user_profile_{request.user.id}"

        # Try to fetch the user profile data from cache
        data = cache.get(cache_key)

        if not data:
            
            # If not found in cache, serialize user data
            serializer = UserSerializer(request.user)
            data = serializer.data

            # Store the serialized data in cache for 15 minutes
            cache.set(cache_key, data, timeout=60 * 100)

        # Return the user profile data (either from cache or fresh)
        return Response(data)

    def patch(self, request):
        user = request.user

        # Use partial=True to allow updating only specific fields
        serializer = UserSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            with transaction.atomic():
                # Save changes to the database atomically
                serializer.save()

                # Invalidate the existing cache entry for the user
                cache.delete(f"user_profile_{user.id}")
                cache.delete(f"user_jwt_{user.id}")
                

            # Return the updated user data
            return Response(serializer.data)

        # Return validation errors if any
        return Response(serializer.errors, status=400)
    




from .utils.deltaexchange import DeltaExchangeClient  # ✅ your client import

class BrokerConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        api_key = request.data.get("api_key")
        api_secret = request.data.get("api_secret")

        if not api_key or not api_secret:
            return Response({"error": "api_key and api_secret are required"}, status=400)

        # 1️⃣ Try connecting to Delta API
        try:
            client = DeltaExchangeClient(api_key, api_secret)
            account_info = client.get_account_info()
        except Exception as e:
            return Response({"error": f"Connection failed: {str(e)}"}, status=400)

        # 2️⃣ Handle Error response
        if not account_info.get("success", False):
            return Response(
                {"error": account_info.get("error", {}).get("code", "Invalid credentials")},
                status=400
            )

        # 3️⃣ Extract result
        result = account_info.get("result", {})
        is_kyc_done = result.get("is_kyc_done", False)
        is_login_enabled = result.get("is_login_enabled", False)

        if not is_kyc_done or not is_login_enabled:
            return Response(
                {
                    "error": "KYC not completed or login disabled.",
                    "kyc_status": is_kyc_done,
                    "login_enabled": is_login_enabled,
                },
                status=400
            )

        # 4️⃣ Store encrypted keys and mark login True
        user: User = request.user
        user.set_api_credentials(api_key, api_secret)
        user.is_login = True
        user.save(update_fields=["api_key", "api_secret", "is_login"])
        cache.delete(f"user_profile_{user.id}")
        cache.delete(f"user_jwt_{user.id}")

        return Response(
            {
                "message": "Broker connected successfully ✅",
                "kyc_status": is_kyc_done,
                "login_enabled": is_login_enabled,
                "user": {
                    "first_name": result.get("first_name"),
                    "last_name": result.get("last_name"),
                    "email": result.get("email"),
                    "account_name": result.get("account_name"),
                },
            },
            status=200,
        )

    def delete(self, request):
        user: User = request.user
        user.api_key = None
        user.api_secret = None
        user.is_login = False
        user.save(update_fields=["api_key", "api_secret", "is_login"])
        cache.delete(f"user_profile_{user.id}")
        cache.delete(f"user_jwt_{user.id}")
        return Response({"message": "Broker disconnected ❌"}, status=200)
    






class WatchlistView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    permission_classes = [IsStaff]

    def get(self, request):
        """Get all watchlist items for logged-in user"""
        cache_key = f"watchlist_{request.user.id}"
        data = cache.get(cache_key)
        if not data:
            watchlist = Watchlist.objects.filter(user=request.user)
            serializer = WatchlistSerializer(watchlist, many=True)
            data = serializer.data
            cache.set(cache_key, data)
        return Response(data)

    def post(self, request):
        """Add symbol to watchlist"""
        symbol_id = request.data.get("symbolid")
        if not symbol_id:
            return Response({"error": "symbolid is required"}, status=400)

        try:
            symbol = SymbolMaster.objects.get(symbolid=symbol_id)
        except SymbolMaster.DoesNotExist:
            return Response({"error": "Symbol not found"}, status=404)

        watchlist, created = Watchlist.objects.get_or_create(user=request.user, symbol=symbol)
        cache_key = f"watchlist_{request.user.id}"
        cache.delete(cache_key)
        if not created:
            return Response({"message": "Symbol already in watchlist"}, status=200)

        serializer = WatchlistSerializer(watchlist)
        return Response(serializer.data, status=201)

    def delete(self, request):
        """Remove symbol from watchlist"""
        symbol_id = request.data.get("symbolid")
        if not symbol_id:
            return Response({"error": "symbolid is required"}, status=400)

        try:
            watchlist_item = Watchlist.objects.get(user=request.user, symbol__symbolid=symbol_id)
            watchlist_item.delete()
            return Response({"message": "Symbol removed from watchlist"}, status=200)
        except Watchlist.DoesNotExist:
            return Response({"error": "Not in watchlist"}, status=404)


from django.utils import timezone
class TradeDetailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradeDetailsSerializer

    def get(self,request):
        cache_key = f"trade_details_{request.user.id}"
        today = timezone.now().date()
        data = cache.get(cache_key)
        if not data:
            trades = tradeDetails.objects.filter(
                owner=request.user,
                # date__date=today
            ).order_by("-date")
            serializer = TradeDetailsSerializer(trades, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
        return Response(data)
    

class OrderDetailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderDetailsSerializer

    def get(self,request):
        cache_key = f"order_details_{request.user.id}"
        today = timezone.now().date()
        data = cache.get(cache_key)
        if not data:
            trades = OrderDetails.objects.filter(
                owner=request.user,
                # date__date=today
            ).order_by("-date")
            serializer = OrderDetailsSerializer(trades, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
        return Response(data)

class HighLowStrategyViewSet1(viewsets.ModelViewSet):
    serializer_class = HighLowStrategySerializer
    cache_list_key = "highlow_strategies"
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return highLowstratergy.objects.all().order_by("-created_date")
    
    # List with cache
    def list(self, request, *args, **kwargs):
        data = cache.get(self.cache_list_key)
        if not data:
            objs = highLowstratergy.objects.all().order_by("-created_date")
            serializer = self.get_serializer(objs, many=True)
            data = serializer.data
            cache.set(self.cache_list_key, data, timeout=300)  # cache for 5 min
        return Response(data)


class HighLowStrategyViewSet(viewsets.ModelViewSet):
    serializer_class = HighLowStrategySerializer
    cache_list_key = "highlow_strategies"
    permission_classes = [IsStaff]

    def get_queryset(self):
        return highLowstratergy.objects.all().order_by("-created_date")
    
    # List with cache
    def list(self, request, *args, **kwargs):
        data = cache.get(self.cache_list_key)
        if not data:
            objs = highLowstratergy.objects.all().order_by("-created_date")
            serializer = self.get_serializer(objs, many=True)
            data = serializer.data
            cache.set(self.cache_list_key, data, timeout=300)  # cache for 5 min
        return Response(data)

    # Retrieve single object with cache
    def retrieve(self, request, *args, **kwargs):
        obj_id = kwargs.get("pk")
        cache_key = f"highlow_strategy_{obj_id}"
        data = cache.get(cache_key)

        if not data:
            try:
                obj = highLowstratergy.objects.get(pk=obj_id)
            except highLowstratergy.DoesNotExist:
                return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.get_serializer(obj)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)

        return Response(data)

    # Create
    def perform_create(self, serializer):
        instance = serializer.save()
        cache.delete(self.cache_list_key)  # invalidate list cache
        return instance

    # Update
    def perform_update(self, serializer):
        instance = serializer.save()
        cache.delete(self.cache_list_key)
        cache.delete(f"highlow_strategy_{instance.id}")
        return instance

    # Delete
    def perform_destroy(self, instance):
        cache.delete(self.cache_list_key)
        cache.delete(f"highlow_strategy_{instance.id}")
        instance.delete()



from datetime import timedelta,datetime
import pytz
import random


from .utils.functions import process_entry_order,process_exit_order

class ProcessSignal(APIView):
    
    def post(self,request,*args, **kwargs):
        text_data = request.body.decode('utf-8')
        
        # param_value = self.request.query_params.get('string', None)
        data = text_data.split("|")
        print(data)
        symbol,symbolid, entry, target, stoploss, strategy_id, stratergycode, tradingbridgecode, side, input_datetime_str, leverage, capital, type,blank = data
        print(symbol, entry, target, stoploss, strategy_id, stratergycode, tradingbridgecode, side, input_datetime_str, leverage, capital, type )
        try:
            input_datetime = datetime.strptime(input_datetime_str, "%m/%d/%Y %I:%M:%S %p")
            tz = pytz.timezone('Asia/Kolkata')
            input_datetime = tz.localize(input_datetime)
            unix_timestamp = int(input_datetime.timestamp())
            # api_timestamp = int(data[10])/1000
            api_timestamp = unix_timestamp
        except:
            input_datetime_str = int(input_datetime_str)/1000
            api_timestamp = input_datetime_str
        ist_timezone = pytz.timezone('Asia/Kolkata')  # IST timezone
        
        api_datetime_utc = datetime.utcfromtimestamp(api_timestamp)
        specific_datetime = api_datetime_utc.replace(tzinfo=pytz.utc).astimezone(ist_timezone)
        cache_key = f"process_signal_{symbol}_{strategy_id}_{side}_{type}"
        if cache.get(cache_key):
            return Response({'message':'Duplicate Signal. Ignored.'})
        cache.set(cache_key, True, timeout=30)  # Cache for 30 seconds
        SignalMaster.objects.create(
            symbol = symbol,
            entry = entry,
            target = target,
            stoploss = stoploss,
            stratergy_id =strategy_id ,
            side = side,
            leverage = leverage,
            capital = capital,
            unique = 111111,
            timestamp = specific_datetime,
            status = "pending"
        )
        if tradingbridgecode == "DELTA" and  highLowstratergy.objects.filter( stratergy_code = stratergycode).exists():
            strat = highLowstratergy.objects.get( stratergy_code = stratergycode)
            if not strat:
                return Response({'message':'Strategy is Inactive. Ignored.'})
           
            if type == "Entry":
                
                
                if adminPosition.objects.filter(Q(strategy_id = strategy_id) & Q(symbol = symbol) & Q(side = side)).exists():
                    if side == "buy":
                        side1 = "sell"
                    else:
                        side1 = "buy"
                    client123 = process_exit_order(strategy_id,symbolid,side1,strat.name)
                    client123.process()
                    client12 = process_entry_order(symbolid,side,leverage,capital,strategy_id,strat.name)
                    client12.process()
                    

                    return Response({'message':'Signal Process Successfully.'})
                else:
                    process_entry_order()
            else:
                client12 = process_exit_order(strategy_id,symbolid,side,strat.name)
                client12.process()
                return Response({'message':'Signal Process Successfully.'})
        else:
            return Response({'message':'Strategy is Inactive. Ignored.'})
        


from datetime import date


class dashboard_count(APIView):
    permission_classes = [IsStaff]

    def post(self, request):
        data = request.data
        userdata = User.objects.all()
        
        # For date range queries
        total_customer = userdata.filter(
            Q(date_joined__date__gt=data['startdate']) & 
            Q(date_joined__date__lt=data['enddate'])
        ).count()
        
        broker_login = userdata.filter(
            Q(date_joined__date__gt=data['startdate']) & 
            Q(date_joined__date__lt=data['enddate']) & 
            Q(is_login=True)
        ).count()
        
        not_login = userdata.filter(
            Q(date_joined__date__gt=data['startdate']) & 
            Q(date_joined__date__lt=data['enddate']) & 
            Q(is_login=False)
        ).count()
        
        # For today's queries
        today_total_customer = userdata.filter(
            date_joined__date=date.today()
        ).count()
        
        today_broker_login = userdata.filter(
            Q(date_joined__date=date.today()) & 
            Q(is_login=True)
        ).count()
        
        today_not_login = userdata.filter(
            Q(date_joined__date=date.today()) & 
            Q(is_login=False)
        ).count()
        
        return Response({
            "total_customer": total_customer,
            "broker_login": broker_login,
            "not_login": not_login,
            "today_total_customer": today_total_customer,
            "today_broker_login": today_broker_login,
            "today_not_login": today_not_login
        })



class user_strategy_portfolio(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        cache_key = f"strategies_user_{request.user.id}"
        data = cache.get(cache_key)
        if not data:
            userdata = userStratergyPortfolio.objects.filter(owner = request.user)
            serializer = UserStrategyPortfolioSerializer(userdata,many=True)
            data = serializer.data
            cache.set(cache_key, data)
        return Response(data)
    


    

class deploy_strategy_portfolio(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data = request.data
        strategyid = data['strategyid']     
        existing_deployment, created = userStratergyPortfolio.objects.get_or_create(
            owner_id=request.user.id,
            stratergy_id=strategyid,
            defaults={'is_active': True}
        )
        
        if not created:
            # Strategy already exists, activate it
            existing_deployment.is_active = True
            existing_deployment.save()
            message = "Strategy reactivated"
        else:
            message = "Strategy deployed successfully"
        response_serializer = UserStrategyPortfolioSerializer(existing_deployment,many=False)
        return Response({
            'status': 'success',
            'message': message,
            'data': response_serializer.data
        }, status=status.HTTP_201_CREATED)
    

class UndeployStrategyAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Undeploy a strategy (set is_active to False)"""
        data = request.data
        strategyid = data['strategyid'] 
        portfolio = userStratergyPortfolio.objects.get(Q(stratergy_id =strategyid ) & Q(owner_id = request.user.id)) 
        
        
        
        portfolio.delete()
        
        response_serializer = UserStrategyPortfolioSerializer(portfolio)
        return Response({
            'status': 'success',
            'message': 'Strategy undeployed successfully',
            'data': response_serializer.data
        })
        

import requests
from .utils.functions import get_live_price


class setSignal(APIView):

    permission_classes = [IsStaff]
    serializer_class = copySignalSerializers

    def get(self,request):
        today = timezone.now().date()

        userdata = copysignal.objects.filter(
            owner=request.user,
           
        )
        data = self.serializer_class(userdata,many=True).data
        return Response(data, status=status.HTTP_200_OK)
    
    def post(self,request):
        data = request.data
        if data['typeq'] == "market":
            tz = pytz.timezone('Asia/Kolkata')
            now = datetime.now(tz)
            formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
            headers = {
                "Content-Type": "text/plain"
            }
            parts2 = [
                data['symbol'],
                str(data['symbolid']),"0","0","0",str(data['strategy_id']),str(data['strategy_code']),"DELTA",data['side'],formatted_datetime,str(data['leverage']),str(data['capital']),"Entry"
            ]
            final_string2 = "|".join(parts2) + "|"
            print(final_string2,data['url'])
            response = requests.post(data['url'], data=final_string2.encode("utf-8"), headers=headers)
            price1 = get_live_price(data['symbol'])
            if data['side'] == "buy":
                tpprice = float(price1) + float(data['trailingpoints'])
            else:
                tpprice = float(price1) - float(data['trailingpoints'])
            copy = copysignal(owner = request.user, symbol = data['symbol'],side = data['side'],target = data['target'],stoploss = data['stoploss'],entry = float(price1),typeq = data['typeq'],strategy_id = data['strategy_id'],url = data['url'],trailingpoints = data['trailingpoints'],status = "Active",trailingprice =tpprice,symbolid = data['symbolid'] ,leverage = data['leverage'],capital = data['capital'])

            copy.save()
            return Response({'message':'order process successfully.'},status=status.HTTP_200_OK)
        
        else:
            if data['side'] == "buy":
                tpprice = float(data['entry']) + float(data['trailingpoints'])
            else:
                tpprice = float(data['entry']) - float(data['trailingpoints'])
            copy = copysignal(owner = request.user, symbol = data['symbol'],side = data['side'],target = data['target'],stoploss = data['stoploss'],entry = float(data['entry']),typeq = data['typeq'],strategy_id = data['strategy_id'],url = data['url'],trailingpoints = data['trailingpoints'],status = "Pending",trailingprice =tpprice,symbolid = data['symbolid'] ,leverage = data['leverage'],capital = data['capital'])

            copy.save()
            return Response({'message':'order process successfully.'},status=status.HTTP_200_OK)
            
class closeSignal(APIView):
    permission_classes = [IsStaff]

    def post(self,request):
        data = request.data
        id = data['id']
        signal = copysignal.objects.get(id = id)
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
        return Response({'message':'Order Signal close Successfully.'},status = status.HTTP_200_OK)



class editPendingSignal(APIView):
    permission_classes = [IsStaff]
    serializer_class = copySignalSerializers


    def post(self,request):
        data = request.data
        id = data['id']
        signal = copysignal.objects.get(id = id)

        if data['typeq'] == "market":
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
            price1 =  get_live_price(signal.symbol)
            signal.target = data['target']
            signal.stoploss = data['stoploss']
            signal.entry = float(price1) 
            signal.trailingpoints = data['trailingpoints']
            signal.typeq = "market"
            signal.status = "Active"
            if signal.side == "buy":
                tpprice = float(price1) +float(data['trailingpoints'])
            else:
                tpprice = float(price1) -float(data['trailingpoints'])
            signal.trailingprice = tpprice
            signal.save()
            return Response({'message':'Order Signal edit Successfully.'},status = status.HTTP_200_OK)
        
        else:
            signal.entry = data['entry']
            signal.target = data['target']
            signal.stoploss = data['stoploss']
            signal.trailingpoints = data['trailingpoints']
            if signal.side == "buy":
                tpprice = float(data['entry']) +float(data['trailingpoints'])
            else:
                tpprice = float(data['entry']) -float(data['trailingpoints'])
            signal.trailingprice = tpprice
            signal.save()
            return Response({'message':'Order Signal edit Successfully.'},status = status.HTTP_200_OK)


class deleteSignal(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data
        id = data['id']
        signal = copysignal.objects.get(id = id)
        signal.status = "Canceled"
        signal.save()
        return Response({'message':'Order Signal delete Successfully.'},status = status.HTTP_200_OK)
    


class editActiveSignal(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data
        id = data['id']
        signal = copysignal.objects.get(id = id)
        signal.target = data['target']
        signal.stoploss = data['stoploss']
        signal.trailingpoints = data['trailingpoints']

        price1 =  get_live_price(signal.symbol)
        if signal.side == "buy":
            tpprice = float(price1) +float(data['trailingpoints'])
        else:
            tpprice = float(price1) -float(data['trailingpoints'])
        signal.trailingprice = tpprice
        signal.save()
        return Response({'message':'Order Signal edit Successfully.'},status = status.HTTP_200_OK)



class get_strategy_data(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        userdata = highLowstratergy.objects.all()
        data = HighLowStrategySerializer1(userdata,many=True).data
        return Response(data)


from .serializers import miniUserStrategyPortfolioSerializer

class user_strategy(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        userdata = userStratergyPortfolio.objects.filter(owner_id = request.user.id)
        serialized_data = miniUserStrategyPortfolioSerializer(userdata, many=True).data
        return Response(serialized_data)


from .utils.functions import get_todays_dates,convert_date_range_to_utc
class adminTradeDetails(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        query = Q()
        start_date = data.get('start_date')
        end_data = data.get('end_date')
        strategy = data.get('strategy')
        owner = data.get('owner')

        if owner:
            query &= Q(owner__phone=owner)
        if strategy:
            query &= Q(stratergy_name=strategy)
        if start_date and end_data:
            s,p =convert_date_range_to_utc(start_date,end_data)
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        else:
            s,p = get_todays_dates()
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        userdata = tradeDetails.objects.filter(query)
        serialized_data = adminTradeSerializer(userdata, many=True).data
        return Response(serialized_data)


class adminPositionDetails(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        query = Q()
        # start_date = data.get('start_date')
        # end_data = data.get('end_date')
        strategy = data.get('strategy')
        owner = data.get('owner')

        if owner:
            query &= Q(owner__phone=owner)
        if strategy:
            query &= Q(stratergy_name=strategy)
        # if start_date and end_data:
        #     s,p =convert_date_range_to_utc(start_date,end_data)
        #     query &= Q(date__gte=s)
        #     query &= Q(date__lte=p)
        # else:
        #     s,p = get_todays_dates()
        #     query &= Q(date__gte=s)
        #     query &= Q(date__lte=p)
        userdata = Position.objects.filter(query)
        serialized_data = PositionSerializer(userdata, many=True).data
        return Response(serialized_data)


class adminOrderDetails(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        query = Q()
        start_date = data.get('start_date')
        end_data = data.get('end_date')
        strategy = data.get('strategy')
        owner = data.get('owner')

        if owner:
            query &= Q(owner__phone=owner)
        if strategy:
            query &= Q(stratergy_name=strategy)
        if start_date and end_data:
            s,p =convert_date_range_to_utc(start_date,end_data)
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        else:
            s,p = get_todays_dates()
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        userdata = OrderDetails.objects.filter(query)
        serialized_data = adminOrderDetailsSerializer(userdata, many=True).data
        return Response(serialized_data)


class userOrderDetails(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        data = request.data
        query = Q()
        start_date = data.get('start_date')
        end_data = data.get('end_date')
        strategy = data.get('strategy')



        query &= Q(owner_id = request.user.id)
        if strategy:
            query &= Q(stratergy_name=strategy)
        if start_date and end_data:
            s,p =convert_date_range_to_utc(start_date,end_data)
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        else:
            s,p = get_todays_dates()
            query &= Q(date__gte=s)
            query &= Q(date__lte=p)
        userdata = OrderDetails.objects.filter(query)
        serialized_data = adminOrderDetailsSerializer(userdata, many=True).data
        return Response(serialized_data)

class admin_user_strategy(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        query = Q()

        customer_phone = data.get('customer_phone')
        strategy = data.get('strategy')
        status = data.get('status')

        if customer_phone:
            query &= Q(owner__phone=customer_phone)

        if strategy:
            query &= Q(stratergy__stratergy_code=strategy)

        if status == "ACTIVE":
            query &= Q(is_active=True)
        elif status == "INACTIVE":
            query &= Q(is_active=False)

        userdata = userStratergyPortfolio.objects.filter(query)
        serialized_data = miniUserStrategyPortfolioSerializer(userdata, many=True).data
        return Response(serialized_data)

    def put(self, request):
        data = request.data
        strategy_id = data['strategy_id']
        status = data['status']
        user_strategy = userStratergyPortfolio.objects.get(id = strategy_id)
        user_strategy.is_active = status
        user_strategy.save()
        return Response({'message':'Strategy updated successfully.'})


from .models import tutorial
from .serializers import tutorialSerializer
class get_tutorial(APIView):

    def get(self,request):
        cache_key = "tutorials"
        data = cache.get(cache_key)
        if not data:
            userdata = tutorial.objects.all()
            serializer = tutorialSerializer(userdata,many=True)
            cache.set(cache_key, serializer.data, timeout=60 * 100)
            return Response(serializer.data)
        return Response(data)
        



class add_strategy(APIView):
  
    def post(self, request):
        data = request.data
        owner = data['owner']
        phone = data['phone']
        email = data['email']
        strategy_name = data['strategy_name']
        trades_per_day = data['trades_per_day']
        timeframe = data['timeframe']
        indicator_name = data['indicator_name']
        target = data['target']
        sl = data['sl']
        entry_condition = data['entry_condition']
        exit_condition = data['exit_condition']
        
        # email1 = "strategy@tradearth.in"
        # email_body ="strategyname :"+ strategyname +"\n"+"\n"+ "strategycategory :"+ strategycategory +"\n"+"\n"+ "segment :"+ segment +"\n"+"\n" + "timeframe :"+ str(timeframe) +"\n"+"\n" + "tradeperday :"+ str(tradeperday) +"\n"+"\n" + "indicators :"+ str(indicators) +"\n"+"\n"+ "entryconditions :"+ str(entryconditions) +"\n"+"\n"+ "exitconditions :"+ str(exitconditions) +"\n"+"\n"+ "stoploss :"+ str(stoploss) +"\n"+"\n"+ "target :"+ str(target) +"\n"+"\n"+ "additionalnotes :"+ str(additionalnotes) +"\n"+"\n"+ "ownername :"+ str(ownername) +"\n"+"\n"+ "whatsappnumber :"+ str(whatsappnumber) +"\n"+"\n"+ "email :"+ str(email) +"\n"+"\n"
        # send_mail('Strategy create request',email_body,"contact@tradearth.in",[email1],)
        return Response({'message':'Strategy Saved Successfully'},status=status.HTTP_200_OK)
        