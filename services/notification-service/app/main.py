from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pika
import redis
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("notification-service")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://localhost:5672/")
NOTIFICATION_TTL_SECONDS = int(os.getenv("NOTIFICATION_TTL_SECONDS", "86400"))

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1.5,
    socket_timeout=1.5,
)
consumer_stop = threading.Event()


def notification_key(user_id: int) -> str:
    return f"notifications:{user_id}"


def initialise_database(max_attempts: int = 12, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            redis_client.ping()
            logger.info("database ready")
            return
        except Exception:
            logger.warning("database not ready (attempt %s/%s)", attempt, max_attempts)
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def save_notification(event: dict) -> None:
    user_id = int(event["userId"])
    notification = {
        "id": str(uuid4()),
        "userId": user_id,
        "orderId": event["orderId"],
        "message": f"Your ShopLite order #{event['orderId']} was created.",
        "createdAt": datetime.now(UTC).isoformat(),
    }
    key = notification_key(user_id)
    pipeline = redis_client.pipeline()
    pipeline.lpush(key, json.dumps(notification))
    pipeline.expire(key, NOTIFICATION_TTL_SECONDS)
    pipeline.execute()
    logger.info(
        "stored notification id=%s for user=%s",
        notification["id"],
        user_id,
    )


def consume_orders() -> None:
    while not consumer_stop.is_set():
        connection = None
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.queue_declare(queue="order-created", durable=True)
            channel.basic_qos(prefetch_count=1)
            logger.info("waiting for order-created messages")

            for method, _, body in channel.consume(
                queue="order-created",
                inactivity_timeout=1,
                auto_ack=False,
            ):
                if consumer_stop.is_set():
                    break
                if method is None:
                    continue
                try:
                    save_notification(json.loads(body))
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:
                    logger.exception("message processing failed: %s", exc)
                    channel.basic_nack(
                        delivery_tag=method.delivery_tag,
                        requeue=True,
                    )
                    time.sleep(1)
            channel.cancel()
        except Exception as exc:
            if not consumer_stop.is_set():
                logger.warning("RabbitMQ unavailable; retrying: %s", exc)
                consumer_stop.wait(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialise_database()
    consumer_stop.clear()
    consumer = threading.Thread(
        target=consume_orders,
        name="order-created-consumer",
        daemon=True,
    )
    consumer.start()
    yield
    consumer_stop.set()
    consumer.join(timeout=3)


app = FastAPI(
    title="ShopLite Notification Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    try:
        redis_client.ping()
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("database readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@router.get("/notifications/{user_id}")
def list_notifications(user_id: int) -> list[dict]:
    try:
        values = redis_client.lrange(notification_key(user_id), 0, -1)
        return [json.loads(value) for value in values]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)
