from django.urls import path
from .views import SendOTPView, LoginView, CheckPhoneView, SignupView

urlpatterns = [
    path('send-otp/', SendOTPView.as_view(), name='send_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-phone/', CheckPhoneView.as_view(), name='check_phone'),
    path('signup/', SignupView.as_view(), name='signup'),
]
