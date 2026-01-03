"""
RabbitMQ - ONE EXCHANGE, ONE QUEUE, ONE CONSUMER
Single producer, single consumer pattern.
Idempotent order handling.
"""
import os
import logging
import json
from typing import Optional, Callable, Dict, Any
try:
    import pika
    from pika import BlockingConnection, ConnectionParameters, BasicProperties
    from pika.exceptions import AMQPConnectionError, AMQPChannelError
    RABBITMQ_AVAILABLE = True
except ImportError:
    RABBITMQ_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("pika not installed - RabbitMQ features disabled")

logger = logging.getLogger(__name__)

# Configuration from environment
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

# Exchange and Queue names
EXCHANGE_NAME = "cryptoarth_orders"
QUEUE_NAME = "order_execution"
ROUTING_KEY = "order.execute"

_connection: Optional[BlockingConnection] = None
_channel = None

def get_connection():
    """Get or create RabbitMQ connection (lazy initialization)"""
    global _connection
    if not RABBITMQ_AVAILABLE:
        return None
    if _connection is None or _connection.is_closed:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            _connection = BlockingConnection(parameters)
            logger.info("RabbitMQ connection established")
        except AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection failed: {e}")
            return None
    return _connection

def get_channel():
    """Get or create RabbitMQ channel"""
    global _channel
    conn = get_connection()
    if conn is None:
        return None
    
    if _channel is None or _channel.is_closed:
        try:
            _channel = conn.channel()
            # Declare exchange (ONE EXCHANGE)
            _channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type="direct",
                durable=True
            )
            # Declare queue (ONE QUEUE)
            _channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True
            )
            # Bind queue to exchange
            _channel.queue_bind(
                exchange=EXCHANGE_NAME,
                queue=QUEUE_NAME,
                routing_key=ROUTING_KEY
            )
            logger.info("RabbitMQ channel and queue setup complete")
        except AMQPChannelError as e:
            logger.error(f"RabbitMQ channel setup failed: {e}")
            return None
    return _channel

def publish_order(order_data: Dict[str, Any]) -> bool:
    """
    Publish order to RabbitMQ (SINGLE PRODUCER)
    Returns True if published successfully, False otherwise
    """
    try:
        channel = get_channel()
        if channel is None:
            logger.warning("RabbitMQ channel not available, order not published")
            return False
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ROUTING_KEY,
            body=json.dumps(order_data),
            properties=BasicProperties(
                delivery_mode=2,  # Make message persistent
                content_type="application/json"
            )
        )
        logger.info(f"Order published to RabbitMQ: {order_data.get('order_id', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Failed to publish order to RabbitMQ: {e}")
        return False

def start_consumer(callback: Callable[[Dict[str, Any]], None]):
    """
    Start single consumer (ONE CONSUMER)
    Callback receives order_data dict
    """
    try:
        channel = get_channel()
        if channel is None:
            logger.error("RabbitMQ channel not available, consumer not started")
            return False
        
        def on_message(ch, method, properties, body):
            """Process incoming message"""
            try:
                order_data = json.loads(body)
                callback(order_data)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in RabbitMQ message: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            except Exception as e:
                logger.error(f"Error processing RabbitMQ message: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
        channel.basic_qos(prefetch_count=1)  # Process one message at a time
        channel.basic_consume(
            queue=QUEUE_NAME,
            on_message_callback=on_message
        )
        
        logger.info("RabbitMQ consumer started")
        channel.start_consuming()
        return True
    except Exception as e:
        logger.error(f"Failed to start RabbitMQ consumer: {e}")
        return False

def close_connection():
    """Close RabbitMQ connection"""
    global _connection, _channel
    try:
        if _channel and not _channel.is_closed:
            _channel.stop_consuming()
            _channel.close()
        if _connection and not _connection.is_closed:
            _connection.close()
        _channel = None
        _connection = None
        logger.info("RabbitMQ connection closed")
    except Exception as e:
        logger.error(f"Error closing RabbitMQ connection: {e}")

