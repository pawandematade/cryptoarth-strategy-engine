from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.cache import cache
import json

User = get_user_model()

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)

class OTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6, min_length=6)

class UserSignupSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(write_only=True, max_length=15)
    otp = serializers.CharField(write_only=True, max_length=6, min_length=6)
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'otp', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        phone = data.get('phone')
        otp = data.get('otp')
        
        # Get OTP from cache
        cached_otp = cache.get(f'otp_{phone}')
        
        if not cached_otp:
            raise serializers.ValidationError({"otp": "OTP expired or not sent"})
        
        # Handle quoted OTPs
        if isinstance(cached_otp, str):
            cached_otp = cached_otp.strip('"').strip("'")
        
        # Compare OTPs
        if str(cached_otp) != str(otp):
            raise serializers.ValidationError({"otp": "Invalid OTP"})
        
        # Delete OTP after successful verification
        cache.delete(f'otp_{phone}')
        
        # Check if user already exists
        if User.objects.filter(username=phone).exists():
            raise serializers.ValidationError({"phone": "User already exists"})
        
        return data

    def create(self, validated_data):
        phone = validated_data.pop('phone')
        validated_data.pop('otp')  # Remove OTP from data
        
        # Create user with phone as username
        user = User.objects.create_user(
            username=phone,
            email=validated_data.get('email', f'{phone}@cryptoarth.in'),
            password=validated_data.get('password'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        
        return user
