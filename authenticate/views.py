from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status , permissions,viewsets
from django.db import transaction, connection

from django.core.cache import cache
from .models import BrokerModels, User,Watchlist, SymbolMaster,highLowstratergy,tradeDetails,OrderDetails,SignalMaster,Position,adminPosition,userStratergyPortfolio,copysignal,SignalMaster
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.exceptions import APIException
from rest_framework.decorators import action
from .serializers import SendOTPSerializer,UserSignupSerializer,OTPLoginSerializer,UserSerializer,WatchlistSerializer,HighLowStrategySerializer,TradeSerializer,OrderDetailsSerializer,UserStrategyPortfolioSerializer,TradeDetailsSerializer,copySignalSerializers,HighLowStrategySerializer1,adminTradeSerializer,adminOrderDetailsSerializer,PositionSerializer,BrokerSerializer

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

from .serializers import MiniStrategySerializer,miniUserSerializer
class get_admin_strategy_list(APIView):
    permission_classes = [IsStaff]
    def get(self, request):
        if request.user.is_staff == True:
            strategy = highLowstratergy.objects.filter(is_active=True)
        else:
            strategy = highLowstratergy.objects.filter(is_active=True,owner = request.user.username)
        data = MiniStrategySerializer(strategy,many=True).data
        return Response(data)
    
class get_admin_user_list(APIView):
    permission_classes = [IsStaff]
    def get(self, request):
        if request.user.is_staff == True:
            userdata = User.objects.all()
        else:
            userdata = User.objects.filter(refercode = request.user.username)
        data = miniUserSerializer(userdata,many=True).data
        return Response(data)  
    

class get_admin_broker_list(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data
        if request.user.is_staff == True:
            brokerdata = BrokerModels.objects.filter(user_id = data['user_id'],status = True)
            data = BrokerSerializer(brokerdata,many = True).data
            return Response(data)
        else:
            if User.objects.filter(id = data['user_id'],refercode = request.user.username).exists():
                brokerdata = BrokerModels.objects.filter(user_id = data['user_id'],status = True)
                data = BrokerSerializer(brokerdata,many = True).data
                return Response(data)
            else:
                return Response({'message':'User not found'}, status = status.HTTP_404_NOT_FOUND)
            

class admin_deploy_user_strategy(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data

        strategyid = data['strategyid']  
        user_id = data['user_id']
        broker_id = data['broker_id']
        try:
            strategy = highLowstratergy.objects.get(id=strategyid)
        except highLowstratergy.DoesNotExist:
            return Response(
                {"error": "Strategy not found", "status": False},
                status=status.HTTP_404_NOT_FOUND
            ) 
        
        existing_symbol_deployments = userStratergyPortfolio.objects.filter(
                owner_id=user_id,
                stratergy__symbol=strategy.symbol,  # Assuming strategy has a 'symbol' field
                is_active=True,
                broker_id = broker_id
            ).exclude(stratergy_id=strategyid)
        
        if existing_symbol_deployments.exists():
            return Response({
                "error": f"You already have an active deployment for symbol '{strategy.symbol}'",
           
                "status": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        existing_deployment, created = userStratergyPortfolio.objects.get_or_create(
            owner_id=user_id,
            stratergy_id=strategyid,
            defaults={'is_active': True},
            broker_id = data.get('broker_id','')
        )
        
        if not created:
            # Strategy already exists, activate it
            existing_deployment.is_active = True
            existing_deployment.save()
            message = "Strategy is already activated."
        else:
            message = "Strategy deployed successfully"
        response_serializer = UserStrategyPortfolioSerializer(existing_deployment,many=False)
        return Response({
            'status': 'success',
            'message': message,
            'data': response_serializer.data
        }, status=status.HTTP_201_CREATED)
    

class admin_undeploy_user_strategy(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data
        strategyid = data['strategyid'] 
        portfolio = userStratergyPortfolio.objects.get(id =strategyid )  
        
        portfolio.delete()

        return Response({
            'status': 'success',
            'message': 'Strategy undeployed successfully',
   
        })
        






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
    permission_classes = [IsStaff]
    def get(self, request, phone):
        if request.user.is_staff == True:
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
        else:
            if request.user.is_vendor == True:
                if User.objects.filter(phone=phone,refercode =request.user.username ).exists():
                    user = User.objects.get(phone=phone,refercode =request.user.username)
                    serializer = UserSerializer(user)
                    return Response(serializer.data)
                else:
                    return Response(
                        {"error": "User with this phone number does not exist or you are not authorized."},
                        status=status.HTTP_404_NOT_FOUND
                    )
            


class Edit_admin_user(APIView):
    permission_classes = [IsStaff]
    
    def put(self, request):
        user_id = request.data.get('id')
        
        if not user_id:
            return Response({"error": "User ID is required"}, status=400)
        
        # Create update dictionary with only provided fields
        update_data = {}
        
        # Text fields (only update if provided and not empty)
        if request.data.get('first_name') is not None:
            update_data['first_name'] = request.data.get('first_name')
        if request.data.get('last_name') is not None:
            update_data['last_name'] = request.data.get('last_name')
        if request.data.get('email') is not None:
            update_data['email'] = request.data.get('email')
        if request.data.get('phone') is not None:
            update_data['phone'] = request.data.get('phone')
        if request.data.get('username') is not None:
            update_data['username'] = request.data.get('username')
        
        # Boolean fields (check if key exists in request, regardless of value)
        # Fixed: using 'is_vendor' instead of 'vendor'
        if 'is_vendor' in request.data:
            update_data['is_vendor'] = request.data.get('is_vendor')
        
        if 'is_user_edit' in request.data:
            update_data['is_user_edit'] = request.data.get('is_user_edit')
        if 'is_user_view' in request.data:
            update_data['is_user_view'] = request.data.get('is_user_view')
        if 'is_strategydetails_view' in request.data:
            update_data['is_strategydetails_view'] = request.data.get('is_strategydetails_view')
        if 'is_open_position_view' in request.data:
            update_data['is_open_position_view'] = request.data.get('is_open_position_view')
        if 'is_close_position_view' in request.data:
            update_data['is_close_position_view'] = request.data.get('is_close_position_view')
        if 'is_order_book' in request.data:
            update_data['is_order_book'] = request.data.get('is_order_book')
        if 'is_pl_report' in request.data:
            update_data['is_pl_report'] = request.data.get('is_pl_report')
        if 'is_create_strategy' in request.data:
            update_data['is_create_strategy'] = request.data.get('is_create_strategy')
        if 'is_watchlist' in request.data:
            update_data['is_watchlist'] = request.data.get('is_watchlist')
        if 'is_admin_strategy' in request.data:
            update_data['is_admin_strategy'] = request.data.get('is_admin_strategy')
        
        # Debug: Print what we're trying to update
        print(f"Updating user {user_id} with data: {update_data}")
        
        # Single database query
        if update_data:
            try:
                updated_count = User.objects.filter(id=user_id).update(**update_data)
                print(f"Updated {updated_count} user(s)")
                
                if updated_count == 0:
                    return Response({"error": "User not found or no changes made"}, status=404)
            except Exception as e:
                print(f"Error updating user: {str(e)}")
                return Response({"error": str(e)}, status=500)
        cache.delete_pattern('admin_user_profile_*')
        cache.delete(f'user_profile_{user_id}')
        cache.delete(f'user_jwt_{user_id}')
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
from .utils.coindcx import coindcxclient  # ✅ your client import



        
class balanceFetch(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        dataset = BrokerModels.objects.filter(user = request.user,status = True)
        brokerlist = []
        if dataset:
            for broker in dataset:
                if broker.broker == "Coindcx":
                    apikey,apisecret = broker.get_api_credentials()
                    client = coindcxclient(api_key=apikey,api_secret=apisecret)
                    balance_data = client.get_wallet_info()
                    conversion_rate = 96
                    balance = float(balance_data)/conversion_rate
                    brokerlist.append({'broker':broker.broker,'user_name':broker.user.first_name,'user_phone':broker.user.phone,'name':broker.name,'balance':balance})
                else:
                    apikey,apisecret = broker.get_api_credentials()
                    client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
                    balance_data = client.get_balances()
                    fund = float(balance_data['result'][0]['available_balance'])
                    brokerlist.append({'broker':broker.broker,'user_name':broker.user.first_name,'user_phone':broker.user.phone,'name':broker.name,'balance':fund})
            return Response(brokerlist)
        else:
            return Response({'message':'No Broker Connected.'},status=400)





class BrokerConnect(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        dataset = BrokerModels.objects.filter(user = request.user,status = True)
        data = BrokerSerializer(dataset, many=True).data
        return Response(data)
    
    def put(self, request):
        data = request.data
        id = data['id']
        broker = BrokerModels.objects.get(id = id)
        broker.status = False
        broker.save()
        return Response({'message':'Broker Deactivate successfully.'})

    def post(self, request):
        api_key = request.data.get("api_key")
        api_secret = request.data.get("api_secret")
        broker = request.data.get("broker")
        name = request.data.get("name","")
        if not api_key or not api_secret:
            return Response({"error": "api_key and api_secret are required"}, status=400)
        if broker == "Coindcx":
            if BrokerModels.objects.filter(api_key =api_key,api_secret=api_secret,status = True ).exists():
                return Response({"error": "Broker already connected"}, status=400)
            else:
                try:
                    client = coindcxclient(api_key, api_secret)
                    account_info = client.get_account_info()
                    coindcx_id = account_info['result']['coindcx_id']
                    if BrokerModels.objects.filter(user = request.user,status = True,coindcx_id = coindcx_id):
                        return Response({"error": "Broker already connected"}, status=400)
                    if account_info['success'] == True:
                        user: User = request.user
                        broker = BrokerModels.objects.create(
                            user=user,
                            name = name,
                            broker=broker,
                            datetime=timezone.now()
                        )
                        broker.set_api_credentials(api_key, api_secret)
                        user.is_login = True
                        user.save()
                        cache.delete(f"user_profile_{user.id}")
                        cache.delete(f"user_jwt_{user.id}")

                        return Response(
                            {
                                "message": "Broker connected successfully ✅"
                            },
                            status=200,
                        )
                    else:
                        return Response({"error": "Invalid credentials"}, status=400)
                except Exception as e:
                    return Response({"error": f"Connection failed: {str(e)}"}, status=400)
        else:
            if BrokerModels.objects.filter(api_key =api_key,api_secret=api_secret,status = True ).exists():
                return Response({"error": "Broker already connected"}, status=400) 
            else:
                try:
                    client = DeltaExchangeClient(api_key, api_secret)
                    account_info = client.get_account_info()
                    
                except Exception as e:
                    return Response({"error": f"Connection failed: {str(e)}"}, status=400)
                if not account_info.get("success", False):
                    return Response(
                        {"error": account_info.get("error", {}).get("code", "Invalid credentials")},
                        status=400
                    )

                # 3️⃣ Extract result
                
                result = account_info.get("result", {})
                nameof = result.get("account_name", "NA")
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
                user: User = request.user
                if nameof == "Main" and BrokerModels.objects.filter(user = user,broker =broker,status = True ).exists():
                    return Response(
                        {
                            "error": "Main Account already added.",
                            "kyc_status": is_kyc_done,
                            "login_enabled": is_login_enabled,
                        },
                        status=400
                    )
                
                broker = BrokerModels.objects.create(
                    user=user,
                    name = name,
                    broker=broker,
                    datetime=timezone.now()
                )
                broker.set_api_credentials(api_key, api_secret)
                user.is_login = True
                user.save()
                cache.delete(f"user_profile_{user.id}")
                cache.delete(f"user_jwt_{user.id}")

                return Response(
                    {
                        "message": "Broker connected successfully ✅"
                    },
                    status=200,
                )
                

      






class BrokerConnectCoindcx(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        api_key = request.data.get("api_key")
        api_secret = request.data.get("api_secret")
        
        if not api_key or not api_secret:
            return Response({"error": "api_key and api_secret are required"}, status=400)
        try:
            client = coindcxclient(api_key, api_secret)
            account_info = client.get_account_info()
            
            if account_info['success'] == True:
                user: User = request.user
                user.set_api_credentials(api_key, api_secret)
                user.is_login = True
                user.broker = "Coindcx"
                user.save(update_fields=["api_key", "api_secret", "is_login","broker"])
                cache.delete(f"user_profile_{user.id}")
                cache.delete(f"user_jwt_{user.id}")

                return Response(
                    {
                        "message": "Broker connected successfully ✅"
                    },
                    status=200,
                )

            else:
                return Response({"error": "Invalid credentials"}, status=400)
        except Exception as e:
            return Response({"error": f"Connection failed: {str(e)}"}, status=400)



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
        user.broker = "DeltaExchange"
        user.save(update_fields=["api_key", "api_secret", "is_login","broker"])
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
        s,p = get_todays_dates()
        data = cache.get(cache_key)
        if not data:
            trades = tradeDetails.objects.filter(
                owner=request.user,
                date__gte = s,
                date__lte = p
                # date__date=today
            ).order_by("-date")
            serializer = TradeDetailsSerializer(trades, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
        return Response(data)
    
from .serializers import SignalMasterSerializer
from django.db.models import F, Sum, DecimalField, ExpressionWrapper

class get_user_pnl(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        sdate, edate =get_todays_dates()
        today_profit  = OrderDetails.objects.filter(date__range=[sdate, edate],owner = request.user).aggregate(total=Sum('profit'))['total'] or 0
        total_profit = OrderDetails.objects.filter(owner = request.user).aggregate(total=Sum('profit'))['total'] or 0
        trades = Position.objects.filter(owner = request.user).count()
        return Response({'today_profit':today_profit,'total_profit':total_profit,'trades':trades})



class get_dashboard_count(APIView):
    permission_classes = [IsStaff]
    def post(self,request):
        data = request.data
        if request.user.is_staff == True:
            startDate = data['startDate']
            endDate = data['endDate']
            sdate, edate = convert_date_range_to_utc(startDate, endDate)
            total_volume = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate])
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            coindcx_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],broker__broker = "Coindcx")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            delta_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],broker__broker = "DeltaExchange")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            try:
                bot_count = userStratergyPortfolio.objects.filter(is_active = True).count()
                positions_count = Position.objects.all().count()
            except:
                bot_count = 0
                positions_count = 0
            total_orders = OrderDetails.objects.filter(date__range=[sdate, edate]).count()
            total_users = User.objects.filter(date_joined__range=[sdate, edate]).count()
            total_profit = OrderDetails.objects.filter(date__range=[sdate, edate]).aggregate(total=Sum('profit'))['total'] or 0
            return Response({'total_volume':total_volume,'total_orders':total_orders,'total_profit':total_profit,'total_users':total_users,'coindcx_margin':coindcx_margin,'delta_margin':delta_margin,'bot_count':bot_count,'positions_count':positions_count})
        else:
            startDate = data['startDate']
            endDate = data['endDate']
            sdate, edate = convert_date_range_to_utc(startDate, endDate)
            total_volume = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate], owner__refercode=request.user.username)
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            delta_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate], owner__refercode=request.user.username,broker__broker = "DeltaExchange")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            coindcx_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate], owner__refercode=request.user.username,broker__broker = "Coindcx")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            try:
                bot_count = userStratergyPortfolio.objects.filter(is_active = True,owner__refercode =request.user.username ).count()
                positions_count = Position.objects.filter(owner__refercode =request.user.username).count()
            except:
                bot_count = 0
                positions_count = 0
            total_orders = OrderDetails.objects.filter(date__range=[sdate, edate],owner__refercode=request.user.username).count()
            total_users = User.objects.filter(date_joined__range=[sdate, edate],refercode =request.user.username ).count()
            total_profit = OrderDetails.objects.filter(date__range=[sdate, edate],owner__refercode=request.user.username).aggregate(total=Sum('profit'))['total'] or 0
            return Response({'total_volume':total_volume,'total_orders':total_orders,'total_profit':total_profit,'total_users':total_users,'coindcx_margin':coindcx_margin,'delta_margin':delta_margin,'bot_count':bot_count,'positions_count':positions_count})


class get_today_dashboard_count(APIView):
    permission_classes = [IsStaff]
    def get(self,request):

        sdate, edate =get_todays_dates()
        if request.user.is_staff == True:
            
            total_volume = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate])
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            delta_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],broker__broker = "DeltaExchange")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            coindcx_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],broker__broker = "Coindcx")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            total_orders = OrderDetails.objects.filter(date__range=[sdate, edate]).count()
            total_users = User.objects.filter(date_joined__range=[sdate, edate]).count()
            total_profit = OrderDetails.objects.filter(date__range=[sdate, edate]).aggregate(total=Sum('profit'))['total'] or 0
            return Response({'total_volume':total_volume,'total_orders':total_orders,'total_profit':total_profit,'total_users':total_users,'coindcx_margin':coindcx_margin,'delta_margin':delta_margin})
        else:
            
            total_volume = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],owner__refercode=request.user.username)
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            delta_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],owner__refercode=request.user.username,broker__broker = "DeltaExchange")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            coindcx_margin = (
                tradeDetails.objects
                .filter(date__range=[sdate, edate],owner__refercode=request.user.username,broker__broker = "Coindcx")
                .aggregate(
                    total=Sum('margin', output_field=DecimalField(max_digits=20, decimal_places=3))
                )
            )['total'] or 0
            total_orders = OrderDetails.objects.filter(date__range=[sdate, edate],owner__refercode=request.user.username).count()
            total_users = User.objects.filter(date_joined__range=[sdate, edate],refercode=request.user.username).count()
            total_profit = OrderDetails.objects.filter(date__range=[sdate, edate],owner__refercode=request.user.username).aggregate(total=Sum('profit'))['total'] or 0
            return Response({'total_volume':total_volume,'total_orders':total_orders,'total_profit':total_profit,'total_users':total_users,'coindcx_margin':coindcx_margin,'delta_margin':delta_margin})
     
from .serializers import SignalMasterSerializer
class signalmasterView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SignalMasterSerializer

    def get(self,request):
        
        s,p = get_todays_dates()
        strategy_ids = (
            userStratergyPortfolio.objects
            .filter(owner=request.user)
            .values_list('stratergy_id', flat=True)
            .distinct()
        )
        signals = SignalMaster.objects.filter(stratergy_id__in=strategy_ids,timestamp__gte = s,timestamp__lte=p)
        
        serializer = SignalMasterSerializer(signals, many=True)
        data = serializer.data

        return Response(data)


class close_open_position_onbroker(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data =request.data
        strategy_id = data['strategy_id']
        symbol = data['symbol']
        symbolmaster = SymbolMaster.objects.get(symbol = symbol)
        users_coindcx = userStratergyPortfolio.objects.filter(stratergy_id = strategy_id,broker__broker = "Coindcx")
        users_delta = userStratergyPortfolio.objects.filter(stratergy_id = strategy_id,broker__broker = "DeltaExchange")
        for user in users_coindcx:
            try:
                apikey,apisecret = user.broker.get_api_credentials()
                client = coindcxclient(api_key=apikey,api_secret=apisecret)
                position = client.get_positions_coindcx(symbol=self.convert_symbol(symbol))
                quantity_balance = self.get_open_position(position, self.convert_symbol(symbol))
                if float(quantity_balance) != 0:
                    if quantity_balance > 0:
                        side = "sell"
                    else:
                        side = "buy"
                    client.place_order_coindcx(side = side,symbol =  self.convert_symbol(symbol),qty=abs(quantity_balance),leverage=50)
            except:
                pass
        
        for user in users_delta:
            try:
                apikey,apisecret = user.broker.get_api_credentials()
                client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)

                position = client.get_positions(product_id=symbolmaster.symbolid)
                if position['success'] == True:
                    quantity_balance = int(position['result']['size'])
                else:
                    quantity_balance = 0
                if float(quantity_balance) != 0:
                    if quantity_balance > 0:
                        side = "sell"
                    else:
                        side = "buy"
                    client.place_order(product_symbol = symbol,side = side,size=abs(quantity_balance))
                    
            except Exception as e:
                print(str(e))
        return Response({'message':'Orders Close Successfully.'})



    def convert_symbol(self,symbol):
        # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
        base_currency = symbol.replace('USD', '')
        return f"B-{base_currency}_USDT"
    

    def get_open_position(self,positions, symbol):
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





class get_open_position(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data =request.data
        strategy_id = data['strategy_id']
        symbol = data['symbol']
        symbolmaster = SymbolMaster.objects.get(symbol = symbol)
        users_coindcx = userStratergyPortfolio.objects.filter(stratergy_id = strategy_id,broker__broker = "Coindcx")
        users_delta = userStratergyPortfolio.objects.filter(stratergy_id = strategy_id,broker__broker = "DeltaExchange")
        dataset = []
        for user in users_coindcx:
            apikey,apisecret = user.broker.get_api_credentials()
            client = coindcxclient(api_key=apikey,api_secret=apisecret)
            position = client.get_positions_coindcx(symbol=self.convert_symbol(symbol))
            quantity_balance = self.get_open_position1(position, self.convert_symbol(symbol))
            if float(quantity_balance) != 0:
                dataset.append({'user_id':user.owner.id,'user_phone':user.owner.phone,'user_name':user.owner.first_name,'broker':user.broker.id,'broker_name':user.broker.broker,'open_quantity':quantity_balance})
        for user in users_delta:
            try:
                apikey,apisecret = user.broker.get_api_credentials()
                client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
                position = client.get_positions(product_id=symbolmaster.symbolid)
                if position['success'] == True:
                    quantity_balance = int(position['result']['size'])
                else:
                    quantity_balance = 0
                if float(quantity_balance) != 0:
                    dataset.append({'user_id':user.owner.id,'user_phone':user.owner.phone,'user_name':user.owner.first_name,'broker':user.broker.id,'broker_name':user.broker.broker,'open_quantity':quantity_balance})
            except Exception as e:
                print(str(e))
        return Response(dataset)

    def convert_symbol(self,symbol):
        # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
        base_currency = symbol.replace('USD', '')
        return f"B-{base_currency}_USDT"
    

    def get_open_position1(self,positions, symbol):
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


class close_delta_position(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data = request.data
        symbol = data['symbol']
        quantity = abs(int(data['quantity']))
        brokerid = data['brokerid']
        user = BrokerModels.objects.get(id=brokerid)
        apikey,apisecret = user.get_api_credentials()
        client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
        side = data['side']
        order = client.place_order(product_symbol = symbol,side = self.side,size=quantity)
        if order['success'] == True:  
            return Response({'message':'Position Closed Successfully.'})
        else:
            return Response({'error':'Error Closing Position.'},status=400)




def convert_ms_to_kolkata_datetime(timestamp_ms: int):
        """
        Converts a Unix timestamp in milliseconds to a datetime object
        in Kolkata timezone (Asia/Kolkata).
        """
        try:
            kolkata_tz = pytz.timezone('Asia/Kolkata')
            return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=kolkata_tz)
        except (ValueError, TypeError):
            return None
        

class close_position_customer(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data = request.data
        id1 = data['position_id']
        position1 = get_object_or_404(Position,id = id1,owner = request.user)
        apikey,apisecret = position1.broker.get_api_credentials()
        if position1.side == "buy":
            side12 = "sell"
        else:
            side12 = "buy"
        if position1.broker.broker == "Coindcx":
            client = coindcxclient(api_key=apikey, api_secret=apisecret)
            position = client.get_positions_coindcx(symbol=position1.symbol)
            quantity_balance = get_open_position1(position, position1.symbol)
            user_qty = float(position1.quantity)
            if position1.side == "buy" and quantity_balance > 0:
                qty = min(user_qty, abs(quantity_balance))

                order = client.place_order_coindcx(side = side12,symbol = position1.symbol,qty=qty,leverage=position1.leverage)
                margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) 
                post = OrderDetails(owner_id = position1.owner.id,orderid = position1.order_id,symbol = position1.symbol,side = position1.side,stratergy = position1.stratergy,date = convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),buyprice = position1.price,sellprice = float(order['result'][0]['price']),buyquantity = position1.quantity,sellquantity = order['result'][0]['total_quantity'],status = "Completed",profit = ((order['result'][0]['total_quantity'] * float(order['result'][0]['price'])) - (float(position1.quantity) * float(position1.price))),stratergy_name =position1.stratergy_name,broker_id = position1.broker.id )
                post.save()
                post1 = tradeDetails(owner_id = position1.owner.id,symbol = position1.symbol,price =float(order['result'][0]['price']),quantity = order['result'][0]['total_quantity'],side = side12,unique = order['result'][0]['id'] ,date = convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),status =order['result']['state'],orderid = position1.order_id,stratergy = position1.stratergy,remark="Order Placed Successfully.", stratergy_name = position1.stratergy_name,margin = margin_used,broker_id = position1.broker.id)
                post1.save()
                position1.delete()
                return Response({'message':'Position closed successfully.'})
            elif position1.side == "sell" and quantity_balance < 0:
                qty = min(user_qty, abs(quantity_balance))

                order = client.place_order_coindcx(side = side12,symbol = position1.symbol,qty=qty,leverage=position1.leverage)
                margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) 
                post = OrderDetails(owner_id = position1.owner.id,orderid = position1.order_id,symbol = position1.symbol,side = position1.side,stratergy = position1.stratergy,date = convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),sellprice = position1.price,buyprice = float(order['result'][0]['price']),sellquantity = position1.quantity,buyquantity = order['result'][0]['total_quantity'],status = "Completed",profit = ((float(position1.quantity) * float(position1.price)) - (order['result'][0]['total_quantity'] * float(order['result'][0]['price']))),stratergy_name =position1.stratergy_name,broker_id = position1.broker.id )
                post.save()
                post1 = tradeDetails(owner_id = position1.owner.id,symbol = position1.symbol,price =float(order['result'][0]['price']),quantity = order['result'][0]['total_quantity'],side = side12,unique = order['result'][0]['id'] ,date = convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),status =order['result']['state'],orderid = position1.order_id,stratergy = position1.stratergy,remark="Order Placed Successfully.", stratergy_name = position1.stratergy_name,margin = margin_used,broker_id = position1.broker.id)
                post1.save()
                position1.delete()
                return Response({'message':'Position closed successfully.'})
            else:
                return Response({'message':'No open positipn find.'})
        else:
            client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
            position = client.get_positions(product_id=position1.symbol)
            if position['success'] == True:
                quantity_balance = int(position['result']['size'])
                user_qty = int(float(position1.quantity))
                if position1.side == "buy" and quantity_balance > 0:
                    qty = min(user_qty, abs(quantity_balance))
                    order = client.place_order(product_symbol = position1.symbol,side = side12,size=qty)
                    symbol = SymbolMaster.objects.get(symbol = position1.symbol)
                    margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * float(symbol.contract_value) 
                    post = OrderDetails(owner_id = position1.owner.id,orderid = position1.order_id,symbol = position1.symbol,side = position1.side,stratergy = position1.stratergy,date = order['result']['created_at'],buyprice = position1.price,sellprice = float(order['result']['average_fill_price']),buyquantity = position1.quantity,sellquantity = order['result']['size'],status = "Completed",profit = ((order['result']['size'] * float(order['result']['average_fill_price'])) - (float(position1.quantity) * float(position1.price))),stratergy_name =position1.stratergy_name,broker_id = position1.broker.id )
                    post.save()
                    post1 = tradeDetails(owner_id = position1.owner.id,symbol = position1.symbol,price =float(order['result']['average_fill_price']),quantity = float(order['result']['average_fill_price']),side = side12,unique = order['result']['id'] ,date = order['result']['created_at'],status =order['result']['state'],orderid = position1.order_id,stratergy = position1.stratergy,remark="Order Placed Successfully.", stratergy_name = position1.stratergy_name,margin = margin_used,broker_id = position1.broker.id)
                    post1.save()
                    position1.delete()
                    return Response({'message':'Position closed successfully.'})
                elif position1.side == "sell" and quantity_balance < 0:
                    qty = min(user_qty, abs(quantity_balance))
                    order = client.place_order(product_symbol = position1.symbol,side = side12,size=qty)
                    margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * float(symbol.contract_value) 
                    post = OrderDetails(owner_id = position1.owner.id,orderid = position1.order_id,symbol = position1.symbol,side = position1.side,stratergy = position1.stratergy,date = order['result']['created_at'],sellprice = position1.price,buyprice = float(order['result']['average_fill_price']),sellquantity = position1.quantity,buyquantity = order['result']['size'],status = "Completed",profit = ((float(position1.quantity) * float(position1.price)) - (order['result']['size'] * float(order['result']['average_fill_price'])) ),stratergy_name =position1.stratergy_name,broker_id = position1.broker.id )
                    post.save()
                    post1 = tradeDetails(owner_id = position1.owner.id,symbol = position1.symbol,price =float(order['result']['average_fill_price']),quantity = float(order['result']['average_fill_price']),side = side12,unique = order['result']['id'] ,date = order['result']['created_at'],status =order['result']['state'],orderid = position1.order_id,stratergy = position1.stratergy,remark="Order Placed Successfully.", stratergy_name = position1.stratergy_name,margin = margin_used,broker_id = position1.broker.id)
                    post1.save()
                    position1.delete()
                    return Response({'message':'Positipn closed successfully.'})
                else:
                    return Response({'message':'No open positipn find.'})









class close_position_byid(APIView):
    permission_classes = [permissions.IsAuthenticated]

    
    def post(self,request):
        data = request.data
        position = Position.objects.get(id = data['id'])
        if position.broker.broker == "Coindcx":
            apikey,apisecret = position.broker.get_api_credentials()
            client = coindcxclient(api_key=apikey, api_secret=apisecret)
            position1 = client.get_positions_coindcx(symbol=position.symbol)
            quantity_balance = get_open_position1(position1, position.symbol)
            user_qty = float(position.quantity)
            if (position.side == "buy" and quantity_balance > 0) or (position.side == "sell" and quantity_balance < 0):
                qty = min(user_qty, abs(quantity_balance))
                if position.side == "buy":
                    side = "sell"
                else:
                    side = "buy"
                order = client.place_order_coindcx(side = side,symbol = position.symbol,qty=qty,leverage=position.leverage)
                if order['success'] == True:
                    pass
                    # post = OrderDetails(owner_id = position.owner.id,orderid = position.order_id,symbol=position.symbol,side = position.side,stratergy = position.stratergy_name,date=convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),buyprice = float(position.price) if position.side == "buy" else float(order['result'][0]['price']),sellprice=,buyquantity=,sellquantity=,status = "Completed",profit =,stratergy_name=position.strategy_name,broker_id=position.broker.id)




class close_coindcx_position(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data = request.data
        symbol = data['symbol']
        quantity = abs(float(data['quantity']))
        brokerid = data['brokerid']
        user = BrokerModels.objects.get(id=brokerid)
        apikey,apisecret = user.get_api_credentials()
        client = coindcxclient(api_key=apikey,api_secret=apisecret)
        side = data['side']
        order = client.place_order_coindcx(side = side,symbol = symbol,qty=quantity,leverage=20)
        if order['success'] == True:
            return Response({'message':'Position Closed Successfully.'})
        else:
            return Response({'error':'Error Closing Position.'},status=400)

from .utils.functions import get_live_price
class get_margin_calculator(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        data = request.data
        liveprice = get_live_price(data['symbol'])
        symbol = SymbolMaster.objects.get(symbol = data['symbol'])
        quantity = ((float(data['capital']) * float(data['leverage']) * (float(data['capitalPercent'])/100)) / liveprice)
        lotSize =int( quantity / float(symbol.contract_value))
        if data['targetType'] == "percent":
            profit = ((float(data['capital']) * float(data['target']))/100) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        else:
            profit = (float(data['capital']) * (float(data['target'])/liveprice)) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        if data['stopLossType'] == "percent":
            loss = ((float(data['capital']) * float(data['stopLoss']))/100) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        else:
            loss = (float(data['capital']) * (float(data['stopLoss'])/liveprice)) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        marginRequired = (float(data['capital'])  * (float(data['capitalPercent'])/100)) 
        riskRewardRatio = profit / loss
        return Response({'profit':profit,'loss':loss,'lotSize':lotSize,'quantity':quantity,'contractValue':symbol.contract_value,'usedCapital':data['capital'],'marginRequired':marginRequired,'riskRewardRatio':riskRewardRatio})

        
class get_margin_calculator1(APIView):
    
    def post(self,request):
        data = request.data
        liveprice = get_live_price(data['symbol'])
        symbol = SymbolMaster.objects.get(symbol = data['symbol'])
        quantity = ((float(data['capital']) * float(data['leverage']) * (float(data['capitalPercent'])/100)) / liveprice)
        lotSize =int( quantity / float(symbol.contract_value))
        if data['targetType'] == "percent":
            profit = ((float(data['capital']) * float(data['target']))/100) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        else:
            profit = (float(data['capital']) * (float(data['target'])/liveprice)) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        if data['stopLossType'] == "percent":
            loss = ((float(data['capital']) * float(data['stopLoss']))/100) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        else:
            loss = (float(data['capital']) * (float(data['stopLoss'])/liveprice)) * (float(data['leverage']) * (float(data['capitalPercent'])/100))
        marginRequired = (float(data['capital'])  * (float(data['capitalPercent'])/100)) 
        riskRewardRatio = profit / loss
        return Response({'profit':profit,'loss':loss,'lotSize':lotSize,'quantity':quantity,'contractValue':symbol.contract_value,'usedCapital':data['capital'],'marginRequired':marginRequired,'riskRewardRatio':riskRewardRatio})

    

class OrderDetailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderDetailsSerializer

    def get(self,request):
        cache_key = f"order_details_{request.user.id}"
        s,p = get_todays_dates()
        data = cache.get(cache_key)
        if not data:
            trades = OrderDetails.objects.filter(
                owner=request.user,
                date__gte = s,
                date__lte = p
            ).order_by("-date")
            serializer = OrderDetailsSerializer(trades, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
        return Response(data)

from .models import latencycheck
from .serializers import latencyCheckSerializer 

class LatencyCheckViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaff]
    # Order by newest first
    queryset = latencycheck.objects.all().order_by('-created_at')
    serializer_class = latencyCheckSerializer
    
    # Disable pagination
    pagination_class = None

class HighLowStrategyViewSet1(viewsets.ModelViewSet):
    serializer_class = HighLowStrategySerializer
    
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return highLowstratergy.objects.all().order_by("-created_date")
    
    # List with cache
    def list(self, request, *args, **kwargs):
        cache_list_key = f"highlow_strategies_{request.user.id}"
        data = cache.get(cache_list_key)
        if not data:
            dataset = highLowstratergy.objects.filter(is_active = True)
            objs = dataset.filter(Q(allowed_users__isnull=True) | Q(allowed_users=self.request.user)).order_by("-created_date")
            serializer = self.get_serializer(objs, many=True)
            data = serializer.data
            cache.set(cache_list_key, data, timeout=300)  # cache for 5 min
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
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
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

from .serializers import HighLowStrategyLimitedSerializer
class HighLowStrategyLimitedCreateView(viewsets.ModelViewSet):
    serializer_class = HighLowStrategyLimitedSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        # You can also set the owner to current user if needed
        instance = serializer.save()
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
        return instance
    
    def perform_update(self, serializer):
        instance = serializer.save()
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
        return instance

    # Delete
    def perform_destroy(self, instance):
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
        instance.delete()




from datetime import timedelta,datetime
import pytz
import random

class change_margin_moode(APIView):
    permission_classes = [IsStaff]
    def get(self,request):
        userdata = User.objects.filter(is_login = True)
        for user in userdata:
            try:
                apikey,apisecret = user.get_api_credentials()
                client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
                client.set_margin_type_portfolio()
            except:
                pass
        return Response({'message':'margin Updated successfully.'})

from .utils.functions import process_entry_order,process_exit_order

class ProcessSignal(APIView):
    
    def post(self,request,*args, **kwargs):
        text_data = request.body.decode('utf-8')
        
        # param_value = self.request.query_params.get('string', None)
        data = text_data.split("|")
        print(data)
        symbol,symbolid, entry, target, stoploss, strategy_id, stratergycode, tradingbridgecode, side, input_datetime_str, leverage, capital, type,blank = data
        
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
            status = "pending",
            type = type
        )
        if tradingbridgecode == "DELTA" and  highLowstratergy.objects.filter( stratergy_code = stratergycode).exists():
            strat = highLowstratergy.objects.get( stratergy_code = stratergycode)
            if not strat:
                return Response({'message':'Strategy is Inactive. Ignored.'})
           
            if type == "Entry":
                
                if side == "buy":
                    side1 = "sell"
                else:
                    side1 = "buy"
                if adminPosition.objects.filter(Q(strategy_id = strategy_id) & Q(symbol = symbol) & Q(side = side1)).exists():
                    
                    client123 = process_exit_order(strategy_id,symbolid,side,strat.name)
                    client123.process()

                    client12 = process_entry_order(symbolid,side,leverage,capital,strategy_id,strat.name)
                    client12.process()
                    

                    return Response({'message':'Signal Process Successfully.'})
                else:
                    print(symbolid,side,leverage,capital,strategy_id,strat.name)
                    client12 = process_entry_order(symbolid,side,leverage,capital,strategy_id,strat.name)
                    client12.process()
                    

                    return Response({'message':'Signal Process Successfully.'})
            else:
                if side == "buy":
                    side1 = "sell"
                else:
                    side1 = "buy"
                if adminPosition.objects.filter(Q(strategy_id = strategy_id) & Q(symbol = symbol) & Q(side = side1)).exists():
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
        if request.user.is_staff == True:
            userdata = User.objects.all()
        else:
            userdata = User.objects.all(refercode = request.user.username)
        
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
        try:
            strategy = highLowstratergy.objects.get(id=strategyid)
        except highLowstratergy.DoesNotExist:
            return Response(
                {"error": "Strategy not found", "status": False},
                status=status.HTTP_404_NOT_FOUND
            ) 
        
        existing_symbol_deployments = userStratergyPortfolio.objects.filter(
                owner_id=request.user.id,
                stratergy__symbol=strategy.symbol,  # Assuming strategy has a 'symbol' field
                is_active=True
            ).exclude(stratergy_id=strategyid)
        
        if existing_symbol_deployments.exists():
            return Response({
                "error": f"You already have an active deployment for symbol '{strategy.symbol}'",
           
                "status": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        existing_deployment, created = userStratergyPortfolio.objects.get_or_create(
            owner_id=request.user.id,
            stratergy_id=strategyid,
            defaults={'is_active': True},
            broker_id = data.get('broker_id','')
        )
        
        if not created:
            # Strategy already exists, activate it
            existing_deployment.is_active = True
            existing_deployment.save()
            message = "Strategy is already activated."
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
        portfolio = userStratergyPortfolio.objects.get(Q(id=strategyid ) & Q(owner_id = request.user.id)) 
        
        
        
        portfolio.delete()
        
        response_serializer = UserStrategyPortfolioSerializer(portfolio)
        return Response({
            'status': 'success',
            'message': 'Strategy undeployed successfully',
            'data': response_serializer.data
        })
        

import requests
from .utils.functions import get_live_price


class Close_all_Positions(APIView):
    permission_classes = [IsStaff]

    def post(self,request):
        data = request.data
        strategy_id = data['strategy_id']
        
        if adminPosition.objects.filter(strategy_id = strategy_id).exists():
            adminposition = adminPosition.objects.get(strategy_id = strategy_id)
            symbol = adminposition.symbol
            symbolid = SymbolMaster.objects.get(symbol = symbol).symbolid
            side = adminposition.side
            stratergycode = adminposition.strategy.stratergy_code
            url = "https://trade-api.cryptoarth.in/auth/signal/"
            tz = pytz.timezone('Asia/Kolkata')
            now = datetime.now(tz)
            formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
            headers = {
                "Content-Type": "text/plain"
            }
            if side == "buy":
                side1 = "sell"
            else:
                side1 = "buy"
            parts2 = [
                    symbol,
                    str(symbolid),"0","0","0",str(strategy_id),str(stratergycode),"DELTA",side1,formatted_datetime,"0","0","Exit"
                ]
            final_string2 = "|".join(parts2) + "|"
                
            response = requests.post(url, data=final_string2.encode("utf-8"), headers=headers)
            return Response({'message':'All Positions closed Successfully.'},status = status.HTTP_200_OK)
        else:
            return Response({'message':'No Active Positions found for this Strategy.'},status = status.HTTP_400_BAD_REQUEST)



class get_referal_link(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        if request.user.refercode:
            user1 = User.objects.get(username =request.user.refercode )
            coindcx_link = user1.coindcx_link
            delta_link = user1.deltaexchange_link
            return Response({'coindcx_link':coindcx_link,'delta_link':delta_link})
        else:
            coindcx_link = "https://www.delta.exchange/?code=CRYPTOARTH"
            delta_link = "https://www.delta.exchange/?code=CRYPTOARTH"
            return Response({'coindcx_link':coindcx_link,'delta_link':delta_link})




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



class get_admin_strategy_data(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        
        userdata = highLowstratergy.objects.filter(owner = request.user.username,trading_type__in=["Manual", "Both"])
        data = HighLowStrategySerializer1(userdata,many=True).data
        return Response(data)

from .serializers import miniUserStrategyPortfolioSerializer

class user_strategy(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        userdata = userStratergyPortfolio.objects.filter(owner_id = request.user.id)
        serialized_data = miniUserStrategyPortfolioSerializer(userdata, many=True).data
        return Response(serialized_data)
    

class admin_strategy_set(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        query = Q()
        strategy = data.get('strategy')

        status = data.get('status')
        
        if strategy:
            query &= Q(name=strategy)
        if status and status == "Inactive":
            query &= Q(is_active=False)
        if status and status == "Active":
            query &= Q(is_active=True)
        if request.user.is_staff != True:
            if request.user.is_vendor == True:
                query &= Q(owner=request.user.username)
        userdata = highLowstratergy.objects.filter(query)
        serialized_data = HighLowStrategySerializer(userdata, many=True).data
        return Response(serialized_data)
    

class user_strategy_set(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        data = request.data
        query = Q(owner = request.user.phone)
        strategy = data.get('strategy')
        

        status = data.get('status')
        
        if strategy:
            query &= Q(name=strategy)
        if status and status == "Inactive":
            query &= Q(is_active=False)
        if status and status == "Active":
            query &= Q(is_active=True)
        userdata = highLowstratergy.objects.filter(query)
        serialized_data = HighLowStrategySerializer(userdata, many=True).data
        return Response(serialized_data)



from django.shortcuts import get_object_or_404   

class add_user_to_strategy(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        data = request.data
        strategy_id = data.get('strategy_id')
        phone_numbers_str = data.get('phone_numbers')
        if request.user.is_staff == True:
            strategy = get_object_or_404(highLowstratergy, id=strategy_id)
        else:
            if request.user.is_vendor == True:
                strategy = get_object_or_404(highLowstratergy, id=strategy_id,owner = request.user.username)
            else:
                strategy = get_object_or_404(highLowstratergy, id=strategy_id,owner = request.user.phone)

        phone_numbers = [phone.strip() for phone in phone_numbers_str.split(',') if phone.strip()]
        if not phone_numbers:
            return Response(
                {"error": "No valid phone numbers provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        users = User.objects.filter(phone__in=phone_numbers)
        if not request.user.is_staff and request.user.is_vendor:
            # Get vendor's username as referral code
            vendor_referral_code = request.user.username
            users = users.filter(refercode=vendor_referral_code)
        found_phones = set(users.values_list('phone', flat=True))
        
        # Check for non-existent phone numbers
        not_found_phones = set(phone_numbers) - found_phones
        
        # Add users to strategy
        strategy.allowed_users.add(*users)
        
        response_data = {
            "message": f"Successfully added {len(users)} users to strategy",
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "added_users": list(found_phones),
            "users_not_found": list(not_found_phones) if not_found_phones else None
        }
        cache.delete_pattern("highlow_strategies_*")
        
        return Response(response_data, status=status.HTTP_200_OK)
    

class remove_user_to_strategy(APIView):
    permission_classes = [IsStaff]
    def post(self, request):
        data = request.data
        strategy_id = data.get('strategy_id')
        phone_numbers_str = data.get('phone_numbers')
        strategy = get_object_or_404(highLowstratergy, id=strategy_id)
        phone_numbers = [phone.strip() for phone in phone_numbers_str.split(',') if phone.strip()]
        if not phone_numbers:
            return Response(
                {"error": "No valid phone numbers provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        users = User.objects.filter(phone__in=phone_numbers)
        found_phones = set(users.values_list('phone', flat=True))
        
        # Check for non-existent phone numbers
        not_found_phones = set(phone_numbers) - found_phones
        
        # Add users to strategy
        strategy.allowed_users.remove(*users)
        response_data = {
            "message": f"Successfully removed {len(users)} users from strategy",
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "removed_users": list(found_phones),
            "users_not_found": list(not_found_phones) if not_found_phones else None
        }
        cache.delete_pattern("highlow_strategies_*")
        return Response(response_data, status=status.HTTP_200_OK)


from .serializers import UserStratSerializer
class StrategyUsersDetailView(APIView):
    permission_classes = [IsStaff]
    
    def get(self, request, strategy_id):
        strategy = get_object_or_404(highLowstratergy, id=strategy_id)
        
        users = strategy.allowed_users.all()
        
        
        serializer = UserStratSerializer(users, many=True)
        
        response_data = {
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "total_users": users.count(),
            "users": serializer.data
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    


class admin_activate_strategy(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        data = request.data
        strategy_id = data.get('id')
        
        if not strategy_id:
            return Response({'error': 'Strategy ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get strategy based on user type
            if request.user.is_staff:
                strategy = highLowstratergy.objects.get(id=strategy_id)
            elif request.user.is_vendor:
                strategy = highLowstratergy.objects.get(id=strategy_id, owner=request.user.username)
            else:
                strategy = highLowstratergy.objects.get(id=strategy_id, owner=request.user.phone)
                
        except highLowstratergy.DoesNotExist:
            return Response({'error': 'Strategy not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        # Only update if strategy exists
        strategy.is_active = True
        strategy.save()
        
        # Clear cache
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
            
        return Response({'message': 'Strategy Activated Successfully.'}, status=status.HTTP_200_OK)


class admin_deactivate_strategy(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        data = request.data
        strategy_id = data['id']
        try:
            # Get strategy based on user type
            if request.user.is_staff:
                strategy = highLowstratergy.objects.get(id=strategy_id)
            elif request.user.is_vendor:
                strategy = highLowstratergy.objects.get(id=strategy_id, owner=request.user.username)
            else:
                strategy = highLowstratergy.objects.get(id=strategy_id, owner=request.user.phone)
                
        except highLowstratergy.DoesNotExist:
            return Response({'error': 'Strategy not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        strategy.is_active = False
        strategy.save()
        try:
            cache.delete_pattern("highlow_strategies_*")
        except:
            pass
        return Response({'message':'Strategy Deactivate Successfully.'})


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
        if request.user.is_staff != True:
            if request.user.is_vendor == True:
                query &= Q(owner__refercode=request.user.username)
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
        if request.user.is_staff != True:
            if request.user.is_vendor == True:
                query &= Q(owner__refercode=request.user.username)
        
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
    

class get_user_positions(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        userdata = Position.objects.filter(owner = request.user)
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
        if request.user.is_staff != True:
            if request.user.is_vendor == True:
                query &= Q(owner__refercode=request.user.username)
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

        if request.user.is_staff != True:
            if request.user.is_vendor == True:
                query &= Q(owner__refercode=request.user.username)

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

# from .models import Tutorial
# from .serializers import TutorialSerializer

class TutorialDetailAPIView(APIView):
    permission_classes = [IsStaff]
    """
    GET: Retrieve a specific tutorial
    PUT: Update a tutorial
    DELETE: Delete a tutorial
    """
    
    def get_object(self, pk):
        return get_object_or_404(tutorial, pk=pk)
    
    def get(self, request, pk):
        tutorial = self.get_object(pk)
        serializer = tutorialSerializer(tutorial)
        return Response(serializer.data)
    
    def post(self, request):
        # Note: For POST, pk is typically not used since we're creating a new object
        serializer = tutorialSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        tutorial = self.get_object(pk)
        serializer = tutorialSerializer(tutorial, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, pk):
        tutorial = self.get_object(pk)
        serializer = tutorialSerializer(tutorial, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        tutorial = self.get_object(pk)
        tutorial.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
        


from django.core.mail import send_mail
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
        
        email1 = "strategy@tradearth.in"
        email_body ="strategyname :"+ strategy_name +"\n"+"\n" + "timeframe :"+ str(timeframe) +"\n"+"\n" + "tradeperday :"+ str(trades_per_day) +"\n"+"\n" + "indicators :"+ str(indicator_name) +"\n"+"\n"+ "entryconditions :"+ str(entry_condition) +"\n"+"\n"+ "exitconditions :"+ str(exit_condition) +"\n"+"\n"+ "stoploss :"+ str(sl) +"\n"+"\n"+ "target :"+ str(target) +"\n"+"\n"+ "ownername :"+ str(owner) +"\n"+"\n"+ "whatsappnumber :"+ str(phone) +"\n"+"\n"+ "email :"+ str(email) +"\n"+"\n"
        send_mail('Strategy create request',email_body,"contact@tradearth.in",[email1],)
        return Response({'message':'Strategy Saved Successfully'},status=status.HTTP_200_OK)


from .models import customer_failorder
from .serializers import NotificationSerializer


class userNotifications(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self,request):
        s,p = get_todays_dates()
        userdata = customer_failorder.objects.filter(Q(owner=request.user.id) & Q(date__gte=s) & Q(date__lte=p))
        data = NotificationSerializer(userdata,many=True).data
        return Response(data)
