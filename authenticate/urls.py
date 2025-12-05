from django.urls import path,include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'highlow-strategies', HighLowStrategyViewSet, basename='highlow-strategy')
router.register(r'highlow-strategies1', HighLowStrategyViewSet1, basename='highlow-strategy')
router.register(r'highlow-strategies-limited', HighLowStrategyLimitedCreateView, basename='highlow-strategy-limited')

# router.register('seller/auth', SellerAuthViewSet, basename='seller-auth')



urlpatterns = [
    # Endpoint to send OTP to user's phone/email (used for both login and signup)
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    
    # Endpoint for user signup with OTP or social login (Google, Facebook, Apple)
    path('signup/', SignupView.as_view(), name='signup'),

    # Endpoint for OTP-based login (returns JWT access and refresh token)
    path('login/', OTPLoginView.as_view(), name='otp-login'),

     path('signal/', ProcessSignal.as_view(), name='ProcessSignal'),

    path('user/', UserDetailView.as_view(), name='user-detail'),
    path('setSignal/',setSignal.as_view(),name="setSignal"),
    path('deleteSignal/',deleteSignal.as_view(),name="deleteSignal"),
    path('editActiveSignal/',editActiveSignal.as_view(),name="editActiveSignal"),
    path('edidPendingSignal/',editPendingSignal.as_view(),name="edidPendingSignal"),
    path('closeSignal/',closeSignal.as_view(),name="closeSignal"),
    path("broker/connect/", BrokerConnectView.as_view(), name="broker-connect"),
    
    
    path("edit_user/", Edit_admin_user.as_view(), name="Edit_admin_user"),
    path("change_margin_moode/", change_margin_moode.as_view(), name="change_margin_moode"),
    path("get_tutorial/", get_tutorial.as_view(), name="get_tutorial"),
    path("get_strategy_data/", get_strategy_data.as_view(), name="get_strategy_data"),
    path("orders/", OrderDetailsView.as_view(), name="orders"),
    path("trades/", TradeDetailsView.as_view(), name="trades"),
    path("dashboard/", dashboard_count.as_view(), name="dashboard_count"),
    path("watchlist/", WatchlistView.as_view(), name="watchlist"),
    path('users/phone/<str:phone>/', UserByPhoneView.as_view(), name='user-by-phone'),
    # Endpoint to check if a user exists by phone number
    path('check-phone/', PhoneCheckView.as_view(), name='check-phone'),

    path('connect1/', BrokerConnect.as_view(), name='BrokerConnect'),
    path('connect/coindcx/', BrokerConnectCoindcx.as_view(), name='broker-connect-coindcx'),
    path('signal-list/', signalmasterView.as_view(), name='signalmasterView'),
    path('Close_all_Positions/', Close_all_Positions.as_view(), name='Close_all_Positions'),
    path('userOrderDetails/', userOrderDetails.as_view(), name='userOrderDetails'),
    path('adminPositionDetails/', adminPositionDetails.as_view(), name='adminPositionDetails'),
    path('adminOrderDetails/', adminOrderDetails.as_view(), name='adminOrderDetails'),
    path('adminTradeDetails/', adminTradeDetails.as_view(), name='adminTradeDetails'),
    path('user/add_strategy/', add_strategy.as_view(), name='add_strategy'),
    path('user/user_strategy/', user_strategy.as_view(), name='user_strategy'),
    path('user/admin_user_strategy/', admin_user_strategy.as_view(), name='admin_user_strategy'),
    path('user/strategies/', user_strategy_portfolio.as_view(), name='user-strategies'),
    
    # Deploy a strategy
    
    path('user/open_position/', get_open_position.as_view(), name='get_open_position'),
    path('user/strategies/deploy/', deploy_strategy_portfolio.as_view(), name='deploy-strategy'),
     path('today_dashboardcount/', get_today_dashboard_count.as_view(), name='get_today_dashboard_count'),
     path('dashboardcount/', get_dashboard_count.as_view(), name='get_today_dashboard_count'),
    
    path('user_strategy_set/', user_strategy_set.as_view(), name='user_strategy_set'),
    path('add_user_to_strategy/', add_user_to_strategy.as_view(), name='add_user_to_strategy'),
    path('remove_user_to_strategy/', remove_user_to_strategy.as_view(), name='remove_user_to_strategy'),
    path('userNotifications/', userNotifications.as_view(), name='userNotifications'),
    path('admin_deactivate_strategy/', admin_deactivate_strategy.as_view(), name='admin_deactivate_strategy'),
    path('admin_activate_strategy/', admin_activate_strategy.as_view(), name='admin_activate_strategy'),
    path('admin_strategy_set/', admin_strategy_set.as_view(), name='admin_strategy_set'),
    path('user/strategies/undeploy/', UndeployStrategyAPIView.as_view(), name='undeploy-strategy'),
    path('strategy/users/<int:strategy_id>/detailed/', StrategyUsersDetailView.as_view(), name='strategy-users-detailed'),
    path('', include(router.urls)),
]

