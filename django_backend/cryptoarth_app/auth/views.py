from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate, login as auth_login, get_user_model
from django.core.cache import cache
from .serializers import PhoneSerializer, OTPSerializer, UserSignupSerializer
import random
import json

User = get_user_model()

class SendOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            
            # Generate OTP
            otp = str(random.randint(100000, 999999))
            
            # Store OTP in cache (plain string, no quotes)
            cache.set(f'otp_{phone}', otp, timeout=300)
            
            # TODO: In production, send SMS via gateway
            print(f"OTP for {phone}: {otp}")
            
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
        
        # Get OTP from cache
        cached_otp = cache.get(f'otp_{phone}')
        
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
        cache.delete(f'otp_{phone}')
        
        # Authenticate and login user
        auth_login(request, user)
        
        return Response({
            "message": "Login successful",
            "user_id": user.id,
            "phone": phone,
            "is_new_user": created
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
