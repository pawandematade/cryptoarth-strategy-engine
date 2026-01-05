"""
Broker Connection Routes
Migrated from cryptoarth_backend/authenticate/views.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from common.db import get_db
from common.auth import get_current_user
from models import User
from models_legacy_trading import BrokerModels
from order.brokers.delta.client import DeltaExchangeClient
from order.brokers.coindcx.client import coindcxclient
from common.security import set_broker_credentials, get_broker_credentials
from common.redis import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


class BrokerConnectRequest(BaseModel):
    api_key: str
    api_secret: str
    name: Optional[str] = None
    broker: Optional[str] = "DeltaExchange"


@router.post("/connect/delta", status_code=status.HTTP_200_OK)
def connect_delta_broker(
    request: BrokerConnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Connect Delta Exchange broker account"""
    try:
        # Check if broker already connected
        existing = db.query(BrokerModels).filter(
            BrokerModels.api_key == request.api_key,
            BrokerModels.api_secret == request.api_secret,
            BrokerModels.status == True
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Broker already connected")
        
        # Test connection
        client = DeltaExchangeClient(request.api_key, request.api_secret)
        account_info = client.get_account_info()
        
        if not account_info.get("success", False):
            raise HTTPException(
                status_code=400,
                detail=account_info.get("error", {}).get("code", "Invalid credentials")
            )
        
        result = account_info.get("result", {})
        is_kyc_done = result.get("is_kyc_done", False)
        is_login_enabled = result.get("is_login_enabled", False)
        
        if not is_kyc_done or not is_login_enabled:
            raise HTTPException(
                status_code=400,
                detail="KYC not completed or login disabled.",
                headers={"kyc_status": str(is_kyc_done), "login_enabled": str(is_login_enabled)}
            )
        
        # Check if main account already exists
        nameof = result.get("account_name", "NA")
        if nameof == "Main":
            existing_main = db.query(BrokerModels).filter(
                BrokerModels.user_id == user.id,
                BrokerModels.broker == "DeltaExchange",
                BrokerModels.status == True
            ).first()
            if existing_main:
                raise HTTPException(status_code=400, detail="Main Account already added.")
        
        # Create broker connection
        broker = BrokerModels(
            user_id=user.id,
            broker="DeltaExchange",
            name=request.name or nameof,
            status=True
        )
        db.add(broker)
        db.flush()
        
        # Encrypt and store credentials
        set_broker_credentials(broker, request.api_key, request.api_secret, db)
        
        # Update user
        user.is_login = True
        db.commit()
        
        # Clear cache
        if redis_client:
            redis_client.delete(f"user_profile_{user.id}")
            redis_client.delete(f"user_jwt_{user.id}")
        
        return {
            "message": "Broker connected successfully ✅",
            "kyc_status": is_kyc_done,
            "login_enabled": is_login_enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error connecting Delta broker: {e}")
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")


@router.post("/connect/coindcx", status_code=status.HTTP_200_OK)
def connect_coindcx_broker(
    request: BrokerConnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Connect CoinDCX broker account"""
    try:
        # Check if broker already connected
        existing = db.query(BrokerModels).filter(
            BrokerModels.api_key == request.api_key,
            BrokerModels.api_secret == request.api_secret,
            BrokerModels.status == True
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Broker already connected")
        
        # Test connection
        client = coindcxclient(request.api_key, request.api_secret)
        account_info = client.get_account_info()
        
        if account_info.get('success') != True:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        
        coindcx_id = account_info['result']['coindcx_id']
        
        # Check if coindcx_id already exists
        existing_id = db.query(BrokerModels).filter(
            BrokerModels.user_id == user.id,
            BrokerModels.status == True,
            BrokerModels.coindcx_id == coindcx_id
        ).first()
        if existing_id:
            raise HTTPException(status_code=400, detail="Broker already connected")
        
        # Create broker connection
        broker = BrokerModels(
            user_id=user.id,
            broker="Coindcx",
            name=request.name or "",
            status=True,
            coindcx_id=coindcx_id
        )
        db.add(broker)
        db.flush()
        
        # Encrypt and store credentials
        set_broker_credentials(broker, request.api_key, request.api_secret, db)
        
        # Update user
        user.is_login = True
        db.commit()
        
        # Clear cache
        if redis_client:
            redis_client.delete(f"user_profile_{user.id}")
            redis_client.delete(f"user_jwt_{user.id}")
        
        return {"message": "Broker connected successfully ✅"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error connecting CoinDCX broker: {e}")
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")


@router.get("/balance", status_code=status.HTTP_200_OK)
def get_broker_balance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch balance for all connected brokers"""
    brokers = db.query(BrokerModels).filter(
        BrokerModels.user_id == user.id,
        BrokerModels.status == True
    ).all()
    
    brokerlist = []
    for broker in brokers:
        try:
            apikey, apisecret = get_broker_credentials(broker)
            if not apikey or not apisecret:
                continue
            
            if broker.broker == "Coindcx":
                client = coindcxclient(api_key=apikey, api_secret=apisecret)
                balance_data = client.get_wallet_info()
                conversion_rate = 96
                balance = float(balance_data) / conversion_rate
                brokerlist.append({
                    'broker': broker.broker,
                    'user_name': user.first_name,
                    'user_phone': user.phone,
                    'name': broker.name,
                    'balance': balance
                })
            else:
                client = DeltaExchangeClient(api_key=apikey, api_secret=apisecret)
                balance_data = client.get_balances()
                fund = float(balance_data['result'][0]['available_balance'])
                brokerlist.append({
                    'broker': broker.broker,
                    'user_name': user.first_name,
                    'user_phone': user.phone,
                    'name': broker.name,
                    'balance': fund
                })
        except Exception as e:
            logger.error(f"Error fetching balance for broker {broker.id}: {e}")
            continue
    
    if not brokerlist:
        raise HTTPException(status_code=400, detail="No Broker Connected.")
    
    return brokerlist
