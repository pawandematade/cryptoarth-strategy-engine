from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from decouple import config
from cryptography.fernet import Fernet, InvalidToken
from datetime import date

# Create your models here.
class UserManager(BaseUserManager):
    def create_user(self, email=None, phone=None, **extra_fields):
        if not phone and not email:
            raise ValueError("User must have either email or phone")
        if email:
            email = self.normalize_email(email)

        user = self.model(email=email, phone=phone, **extra_fields)
        user.set_unusable_password()  # No password needed
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, phone=None, password=None, **extra_fields):
        if not email:
            raise ValueError("Superuser must have an email")

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        user = self.create_user(email=email, phone=phone, **extra_fields)
        user.set_password(password or "admin@123")  # or set a secure one
        user.save(using=self._db)
        return user
    

class User(AbstractBaseUser, PermissionsMixin):
    
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    api_key = models.CharField(max_length=255, blank=True, null=True)
    api_secret = models.CharField(max_length=255, blank=True, null=True)
    is_login = models.BooleanField(default=False)
    


    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []


    objects = UserManager()


    def __str__(self):
        return self.email if self.email else self.phone
    
    def get_tokens(self):
        refresh = RefreshToken.for_user(self)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    
    def set_api_credentials(self, api_key: str, api_secret: str):
        """Encrypt and store API credentials"""
        FERNET_KEY = config('FERNET_KEY', default=None)
        f = Fernet(FERNET_KEY)
        
        self.api_key = f.encrypt(api_key.encode()).decode()
        self.api_secret = f.encrypt(api_secret.encode()).decode()
        self.save(update_fields=["api_key", "api_secret"])

    def get_api_credentials(self):
        """Decrypt and return API credentials"""
        FERNET_KEY = config('FERNET_KEY', default=None)
        f = Fernet(FERNET_KEY)
        try:
            key = f.decrypt(self.api_key.encode()).decode() if self.api_key else None
            secret = f.decrypt(self.api_secret.encode()).decode() if self.api_secret else None
            return key, secret
        except (InvalidToken, AttributeError):
            return None, None
        

class SymbolMaster(models.Model):
    symbol = models.CharField(max_length=50)
    symbolid = models.IntegerField()
    precision = models.IntegerField(null=True, blank=True)
    minimum_qty = models.IntegerField(default=1)
    Type = models.CharField(max_length=50)
    contract_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)




class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="watchlists")  
    symbol = models.ForeignKey("SymbolMaster", on_delete=models.CASCADE, related_name="watchlists")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'symbol')  

    def __str__(self):
        return f"{self.user.username} - {self.symbol.symbol}"
    
class highLowstratergy(models.Model):
    owner = models.CharField(max_length = 25,default = "TRADEARTH")
    stratergy_code = models.CharField(max_length = 55,default = "NA")
    name = models.CharField(max_length = 25,default = "NA")
    full_name  = models.CharField(max_length = 25,default = "NA")
    is_active = models.BooleanField(default=False)
    stratergy_description = models.CharField(max_length = 500,default = "NA")
    tag = models.JSONField(blank=True, null = True)
    captial_requirement = models.TextField(default="NA")
    entry_time = models.TextField(default="NA")
    exit_time = models.TextField(default="NA")
    created_date = models.DateField(default=date.today)
    target = models.TextField(default="NA")
    sl = models.TextField(default="NA")
    risk = models.CharField(max_length = 25,default = "Low")
    overallReturn = models.DecimalField(max_digits = 13,decimal_places = 3, default=0)
    strategy_allow = models.CharField(max_length = 25,default = "All")

    allowed_users = models.ManyToManyField(
        'User', 
        blank=True,
        related_name='allowed_strategies',
        help_text="Users who are allowed to access this strategy"
    )



class userStratergyPortfolio(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="strategy")  
    stratergy = models.ForeignKey(highLowstratergy, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    date = models.DateTimeField(default=date.today)


class Position(models.Model):
    order_id = models.CharField(max_length=255, default="NA")
    symbol = models.CharField(max_length=255, default="NA")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="positions")  
    side = models.CharField(max_length=255, default="NA")
    price = models.DecimalField(max_digits = 13,decimal_places = 3, default=0)
    quantity = models.DecimalField(max_digits = 13,decimal_places = 7, default=0)
    unique = models.CharField(max_length=50, default="NA")
    leverage = models.IntegerField(default=0)
    stratergy = models.CharField(max_length = 15,default = "NA")
    date = models.DateTimeField(default=date.today)
    stratergy_name = models.CharField(max_length = 25,default = "NA")


class adminPosition(models.Model):
    order_id = models.CharField(max_length=255, default="NA")
    symbol = models.CharField(max_length=255, default="NA")
    strategy =  models.ForeignKey(highLowstratergy, on_delete=models.CASCADE)
    side = models.CharField(max_length=255, default="NA")
    leverage = models.IntegerField(default=0)
    capital = models.DecimalField(max_digits = 13,decimal_places = 7, default=0)

class tradeDetails(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trades")  
    symbol = models.CharField(max_length = 35,default = "NA")
    price = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    quantity = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    side = models.CharField(max_length = 15,default = "NA")
    unique = models.CharField(max_length=50, default="NA")
    date = models.DateTimeField(default=date.today)
    status = models.CharField(max_length = 15,default = "NA")
    orderid = models.CharField(max_length = 35,default = "NA")
    stratergy = models.CharField(max_length = 15,default = "NA")
    remark = models.CharField(max_length = 85,default = "NA")
    stratergy_name = models.CharField(max_length = 25,default = "NA")


class OrderDetails(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")  
    symbol = models.CharField(max_length = 35,default = "NA")
    stratergy = models.CharField(max_length = 15,default = "NA")
    buyprice = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    sellprice = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    buyquantity = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    sellquantity = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    side =  models.CharField(max_length = 15,default = "NA")
    orderid =  models.CharField(max_length = 15,default = "NA")
    date = models.DateTimeField(default=date.today)
    status = models.CharField(max_length = 15,default = "NA")
    profit = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    stratergy_name = models.CharField(max_length = 25,default = "NA")


class customer_failorder(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="failure")
    orderid = models.CharField(max_length = 35,default = "NA")
    strategy = models.CharField(max_length = 35,default = "NA")
    remarks = models.CharField(max_length = 105,default = "NA")
    date = models.DateTimeField(default=timezone.now)



class SignalMaster(models.Model):
    stratergy = models.ForeignKey(highLowstratergy, on_delete=models.CASCADE)
    symbol = models.CharField(max_length = 25,default = "NA")
    side = models.CharField(max_length = 25,default = "NA")
    unique = models.IntegerField(default=0)
    timestamp = models.DateTimeField(default=date.today)
    status = models.CharField(max_length = 25,default = "NA")
    entry = models.DecimalField(max_digits=13,decimal_places=2,default = 0)
    target = models.DecimalField(max_digits=13,decimal_places=2,default = 0)
    stoploss  = models.DecimalField(max_digits=13,decimal_places=2,default = 0)
    leverage = models.IntegerField(default=0)
    capital = models.DecimalField(max_digits=13,decimal_places=2,default = 0)
    type = models.CharField(max_length = 25,default = "NA")  # Entry or Exit





class copysignal(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="copysignal") 
    symbol = models.CharField(max_length = 25,default = "NA")
    symbolid = models.IntegerField(default = 0)
    side = models.CharField(max_length = 15,default = "NA")
    target = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    stoploss = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    entry = models.DecimalField(max_digits=13,decimal_places=3,default = 0)
    typeq  = models.CharField(max_length = 15,default = "NA")
    leverage = models.IntegerField(default=0)
    capital = models.DecimalField(max_digits=13,decimal_places=2,default = 0)
    strategy = models.ForeignKey(highLowstratergy, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length = 105,default = "NA")
    status = models.CharField(max_length = 45,default = "NA")
    trailingpoints = models.IntegerField(default=0)
    trailingprice = models.DecimalField(max_digits=13,decimal_places=3,default = 0)




class tutorial(models.Model):
    title =  models.CharField(max_length = 250,default = "NA")
    description = models.TextField(default="NA")
    link =  models.CharField(max_length = 100,default = "NA")