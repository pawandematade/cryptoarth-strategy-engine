from django.core.cache import cache  # ✅ This is correct

from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import User,SymbolMaster,highLowstratergy,tradeDetails,OrderDetails,userStratergyPortfolio,Position,copysignal,tutorial,customer_failorder,SignalMaster
from rest_framework.exceptions import AuthenticationFailed
import random
from .utils.otp_service import OTPService
from django.db import transaction, connection



class UserSignupSerializer(serializers.ModelSerializer):
    """
    Serializer for user signup process.
    Includes token fields that will be generated after successful signup.
    """
    
    # Read-only token fields that will be populated after user creation
    access = serializers.CharField(max_length=68, min_length=6, read_only=True)
    refresh = serializers.CharField(max_length=68, min_length=6, read_only=True)
    # Add OTP field to the serializer
    otp = serializers.CharField(max_length=6, min_length=6, write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['phone', 'email', 'first_name', 'last_name', 'otp', 'access', 'refresh']

    def validate(self, attrs):
        """
        Validate that the email and phone number are unique before creating a new user.
        Raises AuthenticationFailed if either email or phone already exists.
        """
        email = attrs.get('email', '')
        phone = attrs.get('phone', '')
        otp = attrs.get('otp', '')

        # Check if email already exists
        if User.objects.filter(email=email).exists():
            raise AuthenticationFailed({
                'message': 'The email is already taken',
                'status': False
            })
        
        # Check if phone number already exists
        if User.objects.filter(phone=phone).exists():
            raise AuthenticationFailed({
                'message': 'The phone no. is already taken',
                'status': False
            })
        
        # Validate OTP presence
        if not otp:
            raise AuthenticationFailed({
                'message': 'OTP is required',
                'status': False
            })
        
        # Check OTP from cache
        cached_otp_data = cache.get(f"otp_{phone}")
        if not cached_otp_data:
            raise AuthenticationFailed({
                'message': 'OTP expired or not found.',
                'status': False
            })
        
        if cached_otp_data.get('otp') != otp:
            raise AuthenticationFailed({
                'message': "Invalid OTP.",
                'status': False
            })
        
        # Remove OTP from validated data as it's not needed for user creation
        attrs.pop('otp')
        
        return attrs
    
    def create(self, validated_data):
        """
        Create a new user with the validated data.
        Uses transaction.atomic to ensure data consistency.
        Returns user object along with access and refresh tokens.
        """
        try:
            # Start atomic transaction to ensure all operations complete successfully
            with transaction.atomic():
                # Create user with the provided validated data
                user = User.objects.create_user(**validated_data)
                # Generate JWT tokens for the new user
                tokens = user.get_tokens()
                
                # Delete OTP from cache after successful verification
                phone = validated_data.get('phone')
                cache.delete(f"otp_{phone}")
                
                return {
                    "user": user,
                    "access": tokens['access'],
                    "refresh": tokens['refresh']
                }
        except Exception as e:
            # Log the exception for debugging
            print(f"Error creating user: {str(e)}")
            raise
        finally:
            # Ensure database connection is closed after operation
            connection.close()

class SendOTPSerializer(serializers.Serializer):
    """
    Serializer for sending OTP to a phone number.
    Creates or retrieves user, generates OTP, and sends it via multiple providers.
    """
    
    phone = serializers.CharField(max_length=15)

    def validate(self, data):
        """
        Validate phone number and send OTP.
        Creates user if not exists, generates OTP, and sends via configured providers.
        """
        phone = data.get("phone")
        
        # Basic phone number validation
        if not phone:
            raise serializers.ValidationError("Phone number is required.")

        try:
            # Start atomic transaction
            with transaction.atomic():
                
                
                # Generate 6-digit random OTP
                otp = str(random.randint(100000, 999999))
                
                created_at = timezone.now()

                # Store OTP and timestamp in cache for 5 minutes
                cache.set(f"otp_{phone}", {"otp": otp, "created_at": str(created_at)}, timeout=300)
                
                # Send OTP via both providers for redundancy
                try:
                    OTPService(phone, otp).send_otp(provider="msg91")
                except Exception as e:
                    print(str(e))
                try:
                    print(phone)
                    OTPService(phone, otp).send_otp(provider="aisensy")
                except Exception as e:
                    print(str(e))

                return {"message": "OTP sent successfully."}
        except Exception as e:
            # Handle any errors during OTP sending process
            raise serializers.ValidationError(f"Failed to send OTP. Error: {str(e)}")
        finally:
            # Ensure database connection is closed after operation
            connection.close()




class OTPLoginSerializer(serializers.Serializer):
    """
    Serializer for OTP-based login process.
    Validates phone number and OTP, then returns authentication tokens.
    """
    
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6)
    # Read-only token fields that will be populated after successful validation
    access = serializers.CharField(max_length=68, min_length=6, read_only=True)
    refresh = serializers.CharField(max_length=68, min_length=6, read_only=True)

    def validate(self, data):
        """
        Validate the provided OTP against the stored OTP for the user.
        Checks OTP existence, correctness, and expiration.
        Returns user object and tokens if validation succeeds.
        """
        phone = data.get("phone")
        otp = data.get("otp")
        
        try:
            # Start atomic transaction
            with transaction.atomic():
                cached = cache.get(f"otp_{phone}")
                # Check if OTP exists and matches
                if not cached:
                    raise serializers.ValidationError("OTP expired or not found.")
                if cached['otp'] != otp:
                    raise serializers.ValidationError("Invalid OTP.")
                # Get user by phone number
                user = User.objects.get(phone=phone)
                # if user.role == "seller" or user.role == "manufacturer":
                #     seller1 = Seller.objects.get(user = user)
                #     if seller1.is_verified == False:
                #         raise serializers.ValidationError("You are not verified yet")
                # Generate JWT tokens for the authenticated user
                tokens = user.get_tokens()
                
                return {
                    "user": user,
                    "access": tokens['access'],
                    "refresh": tokens['refresh']
                }
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        finally:
            # Ensure database connection is closed after operation
            connection.close()



class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
        # exclude = ['api_key', 'api_secret']

    def update(self, instance, validated_data):
        # Fields that should NOT be updated
        restricted_fields = [
            "is_staff"
        ]

        for field in restricted_fields:
            if field in validated_data:
                validated_data.pop(field)

        return super().update(instance, validated_data)
    



    

class SymbolMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SymbolMaster
        fields = '__all__'


from .models import Watchlist

class WatchlistSerializer(serializers.ModelSerializer):
    symbol = SymbolMasterSerializer(read_only=True)

    class Meta:
        model = Watchlist
        fields = ['id', 'user', 'symbol', 'created_at']
        read_only_fields = ['id', 'created_at']



class HighLowStrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = highLowstratergy
        fields = '__all__'


class HighLowStrategyLimitedSerializer(serializers.ModelSerializer):
    class Meta:
        model = highLowstratergy
        fields = '__all__'
    
    def create(self, validated_data):
        # Force strategy_allow to be "limited" for non-admin users
        validated_data['strategy_allow'] = 'limited'
        request = self.context.get('request')
        if request:
            validated_data['owner'] = request.user.phone
        # If you want to automatically add the creating user to allowed_users
        strategy = super().create(validated_data)
        
        # Add the current user to allowed_users
        
        if request:
            strategy.allowed_users.add(request.user)
        
        return strategy
    
    def update(self, instance, validated_data):
        # Prevent non-admin users from changing strategy_allow to anything other than "limited"
        if 'strategy_allow' in validated_data:
            if validated_data['strategy_allow'] != 'limited':
                validated_data['strategy_allow'] = 'limited'
        
        return super().update(instance, validated_data)


class HighLowStrategySerializer1(serializers.ModelSerializer):
    class Meta:
        model = highLowstratergy
        fields = ['id','name','stratergy_code']

class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = tradeDetails
        fields = '__all__'

class SignalMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalMaster
        fields = '__all__'


class OrderDetailsSerializer(serializers.ModelSerializer):
    local_date = serializers.SerializerMethodField()

    class Meta:
        model = OrderDetails
        fields = '__all__'

    def get_local_date(self, obj):
        if obj.date:
            utc_time = obj.date
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None


class UserStrategyPortfolioSerializer(serializers.ModelSerializer):

    owner = UserSerializer(read_only = True)
    stratergy = HighLowStrategySerializer(read_only = True)
    class Meta:
        model = userStratergyPortfolio

        fields = ['id','owner','stratergy','is_active']


class PositionSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only = True)
    local_date = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = ['id','order_id','symbol','owner','price','quantity','side','unique','leverage','date','stratergy', 'local_date','stratergy_name']

    def get_local_date(self, obj):
        if obj.date:
            utc_time = obj.date
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    

import pytz
class TradeDetailsSerializer(serializers.ModelSerializer):
    local_date = serializers.SerializerMethodField()

    class Meta:
        model = tradeDetails
        fields = [
            'id', 'owner', 'symbol', 'price', 'quantity', 'side',
            'unique', 'date', 'local_date', 'status', 'orderid',
            'stratergy', 'remark'
        ]

    def get_local_date(self, obj):
        if obj.date:
            utc_time = obj.date
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    

class copySignalSerializers(serializers.ModelSerializer):
    local_date = serializers.SerializerMethodField()

    class Meta:
        model = copysignal
        fields = ['id', 'owner','symbol','symbolid','side','target','stoploss','entry','typeq','strategy','created_at','url','status','trailingpoints','trailingprice','local_date']


    def get_local_date(self, obj):
        if obj.created_at:
            utc_time = obj.created_at
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    




class miniUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone','first_name','last_name','is_login']


class miniUserStrategyPortfolioSerializer(serializers.ModelSerializer):

    owner = miniUserSerializer(read_only = True)
    stratergy = HighLowStrategySerializer(read_only = True)
    class Meta:
        model = userStratergyPortfolio

        fields = ['id','owner','stratergy','is_active']


class tutorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = tutorial
        fields = '__all__'



class adminTradeSerializer(serializers.ModelSerializer):
    local_date = serializers.SerializerMethodField()
    owner = miniUserSerializer(read_only = True)
    class Meta:
        model = tradeDetails
        fields = ['owner','symbol','price','quantity','side','unique','date','status','orderid','stratergy','remark','stratergy_name', 'local_date']

    def get_local_date(self, obj):
        if obj.date:
            utc_time = obj.date
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None


class adminOrderDetailsSerializer(serializers.ModelSerializer):
    local_date = serializers.SerializerMethodField()
    owner = miniUserSerializer(read_only = True)
    class Meta:
        model = OrderDetails
        fields = ['owner','symbol','stratergy','buyprice','sellprice','buyquantity','sellquantity','side','orderid','date','status','profit','stratergy_name', 'local_date']

    def get_local_date(self, obj):
        if obj.date:
            utc_time = obj.date
            ist_timezone = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist_timezone)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None



class NotificationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = customer_failorder
        fields = '__all__'





class UserStratSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone', 'first_name', 'last_name']

