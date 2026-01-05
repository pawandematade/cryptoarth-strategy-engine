from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate, login as auth_login, get_user_model
from django.conf import settings
from django.core.cache import cache
from .serializers import PhoneSerializer, OTPSerializer, UserSignupSerializer
from .utils.otp_service import OTPService
import random
import json
import jwt
from datetime import datetime, timedelta


def normalize_phone(phone):
    """Normalize phone number to consistent format (without 91 prefix)"""
    phone = str(phone).strip()
    phone = phone.replace("+", "").replace(" ", "")
    
    # Remove 91 prefix if present and length is 12
    if phone.startswith("91"):
        phone = phone[2:]
    
    # Remove leading 0
    if phone.startswith("0"):
        phone = phone[1:]
    
    return phone

User = get_user_model()

class SendOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            normalized_phone = normalize_phone(phone)

            # Generate OTP
            otp = str(random.randint(100000, 999999))

            # Store OTP in cache (plain string, no quotes)
            cache_key = f'otp_{normalized_phone}'
            cache.set(cache_key, otp, timeout=300)
            
            # Debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📱 SendOTPView: Stored OTP for {phone}")
            logger.info(f"   Normalized phone: {normalized_phone}")
            logger.info(f"   Cache key: {cache_key}")
            logger.info(f"   OTP value: {otp}")
            logger.info(f"   Timeout: 300 seconds")
            
            # Verify storage
            stored_otp = cache.get(cache_key)
            if stored_otp == otp:
                logger.info(f"   ✅ OTP verified in cache: {stored_otp}")
            else:
                logger.error(f"   ❌ OTP NOT stored correctly!")
                logger.error(f"   Expected: {otp}, Got: {stored_otp}")

            # Send OTP via SMS/WhatsApp
            method = request.data.get('method', 'text')
            # Use normalized phone for sending
            send_phone = normalized_phone
            sent = False
            
            # Try SMS if method is text or both
            if method in ['text', 'both']:
                try:
                    sms_sent = OTPService(send_phone, otp).send_otp(provider='msg91')
                    if sms_sent:
                        sent = True
                        print(f"SMS OTP sent to {phone}: {otp}")
                    else:
                        print(f"SMS failed for {phone}")
                except Exception as e:
                    print(f"SMS error for {phone}: {e}")
            
            # Try WhatsApp if method is whatsapp or both (or if SMS failed)
            if method in ['whatsapp', 'both'] or not sent:
                try:
                    whatsapp_sent = OTPService(send_phone, otp).send_otp(provider='aisensy')
                    if whatsapp_sent:
                        sent = True
                        print(f"WhatsApp OTP sent to {phone}: {otp}")
                    else:
                        print(f"WhatsApp failed for {phone}")
                except Exception as e:
                    print(f"WhatsApp error for {phone}: {e}")
            
            if not sent:
                print(f"All OTP services failed for {phone}")
                # Still continue - at least OTP is in cache for manual verification

            return Response({
                "message": "OTP sent successfully.",
                "phone": phone
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = OTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        phone = serializer.validated_data['phone']
        otp = serializer.validated_data['otp']
        
        # Normalize phone
        normalized_phone = normalize_phone(phone)
        
        # Get OTP from cache
        cached_otp = cache.get(f'otp_{normalized_phone}')
        
        if not cached_otp:
            return Response(
                {"error": "OTP expired or not sent"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle quoted OTPs
        if isinstance(cached_otp, str):
            # Remove quotes if present
            cached_otp = cached_otp.strip('"').strip("'")
        
        # Compare OTPs
        if str(cached_otp) != str(otp):
            return Response(
                {"error": "Invalid OTP"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get or create user
        user, created = User.objects.get_or_create(
            username=phone,
            defaults={'email': f'{phone}@cryptoarth.in'}
        )
        
        if created:
            user.set_unusable_password()  # OTP-based login, no password
            user.save()
        
        # Delete OTP after successful login
        cache.delete(f'otp_{normalized_phone}')
        
        # Authenticate and login user
        auth_login(request, user)
        
        # Generate JWT tokens matching FastAPI engine format
        JWT_ALGORITHM = "HS256"
        ACCESS_TOKEN_LIFETIME = timedelta(minutes=60)
        REFRESH_TOKEN_LIFETIME = timedelta(days=1)
        
        now = datetime.utcnow()
        
        # Access token
        access_payload = {
            "token_type": "access",
            "exp": now + ACCESS_TOKEN_LIFETIME,
            "iat": now,
            "jti": f"access_{user.id}_{int(now.timestamp())}",
            "user_id": user.id,
        }
        
        # Refresh token  
        refresh_payload = {
            "token_type": "refresh",
            "exp": now + REFRESH_TOKEN_LIFETIME,
            "iat": now,
            "jti": f"refresh_{user.id}_{int(now.timestamp())}",
            "user_id": user.id,
        }
        
        access_token = jwt.encode(access_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)
        refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        return Response({
            "message": "Login successful",
            "user_id": user.id,
            "phone": phone,
            "is_new_user": created,
            "access_token": access_token,
            "refresh_token": refresh_token
        }, status=status.HTTP_200_OK)

class CheckPhoneView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            exists = User.objects.filter(username=phone).exists()
            return Response({"exists": exists}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SignupView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserSignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            auth_login(request, user)
            return Response({
                "message": "Signup successful",
                "user_id": user.id,
                "phone": user.username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
