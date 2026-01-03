"""
Lightweight Latency Tracker
Tracks: signal receive → broker response
Per order, per customer, per broker
"""
import time
import json
import logging
from typing import Dict, Optional, List
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

class LatencyTracker:
    """
    Lightweight latency tracking for order execution flow
    Tracks key milestones: signal → MQ → broker → response
    """
    
    @staticmethod
    def start_timing(order_id: str, signal_time: Optional[float] = None) -> Dict[str, float]:
        """
        Start timing for an order
        Returns timing dict with signal_received timestamp
        """
        timing = {
            "order_id": order_id,
            "signal_received": signal_time or time.time(),
            "mq_enqueued": None,
            "mq_dequeued": None,
            "broker_request_sent": None,
            "broker_response_received": None,
            "order_status_final": None,
        }
        return timing
    
    @staticmethod
    def mark_mq_enqueued(timing: Dict[str, float]):
        """Mark when order was enqueued to RabbitMQ"""
        timing["mq_enqueued"] = time.time()
    
    @staticmethod
    def mark_mq_dequeued(timing: Dict[str, float]):
        """Mark when order was dequeued from RabbitMQ"""
        timing["mq_dequeued"] = time.time()
    
    @staticmethod
    def mark_broker_request_sent(timing: Dict[str, float]):
        """Mark when broker request was sent"""
        timing["broker_request_sent"] = time.time()
    
    @staticmethod
    def mark_broker_response_received(timing: Dict[str, float]):
        """Mark when broker response was received"""
        timing["broker_response_received"] = time.time()
    
    @staticmethod
    def mark_order_status_final(timing: Dict[str, float]):
        """Mark when order status became final"""
        timing["order_status_final"] = time.time()
    
    @staticmethod
    def calculate_latencies(timing: Dict[str, float]) -> Dict[str, Optional[float]]:
        """
        Calculate latency metrics from timing dict
        Returns dict with latency in seconds
        """
        signal = timing.get("signal_received")
        mq_enq = timing.get("mq_enqueued")
        mq_deq = timing.get("mq_dequeued")
        broker_req = timing.get("broker_request_sent")
        broker_resp = timing.get("broker_response_received")
        final = timing.get("order_status_final")
        
        latencies = {
            "signal_to_mq": mq_enq - signal if signal and mq_enq else None,
            "mq_queue_time": mq_deq - mq_enq if mq_enq and mq_deq else None,
            "mq_to_broker": broker_req - mq_deq if mq_deq and broker_req else None,
            "broker_response_time": broker_resp - broker_req if broker_req and broker_resp else None,
            "total_time": final - signal if signal and final else None,
        }
        return latencies
    
    @staticmethod
    def store_timing(order_id: str, timing: Dict[str, float], user_id: Optional[str] = None, broker: Optional[str] = None):
        """
        Store timing data (optional - uses Redis if available)
        Non-fatal if Redis is unavailable
        """
        redis = get_redis()
        if redis is None:
            # Redis not available - just log
            logger.debug(f"Timing data not stored (Redis unavailable): {order_id}")
            return
        
        try:
            timing_data = {
                **timing,
                "latencies": LatencyTracker.calculate_latencies(timing),
                "user_id": user_id,
                "broker": broker,
                "timestamp": datetime.utcnow().isoformat()
            }
            key = f"latency:{order_id}"
            redis.setex(key, 86400, json.dumps(timing_data))  # Store for 24 hours
        except Exception as e:
            logger.warning(f"Failed to store timing data (non-fatal): {e}")

# Global instance
latency_tracker = LatencyTracker()

