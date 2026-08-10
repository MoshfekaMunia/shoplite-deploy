from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pika
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("order-service")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orders.db")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8002")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://localhost:5672/")
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "3"))

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notification_queued: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class OrderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: int = Field(alias="userId", gt=0)
    product_id: str = Field(alias="productId", min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=100)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int = Field(serialization_alias="userId")
    product_id: str = Field(serialization_alias="productId")
    quantity: int
    unit_price: Decimal = Field(serialization_alias="unitPrice")
    total: Decimal
    created_at: datetime = Field(serialization_alias="createdAt")
    notification_queued: bool = Field(
        default=True, serialization_alias="notificationQueued"
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialise_database(max_attempts: int = 12, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("database ready")
            return
        except Exception:
            logger.warning("database not ready (attempt %s/%s)", attempt, max_attempts)
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def fetch_dependency(url: str, dependency_name: str) -> dict:
    try:
        response = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    except httpx.RequestError as exc:
        logger.warning("%s request failed: %s", dependency_name, exc)
        raise HTTPException(
            status_code=503,
            detail=f"{dependency_name} service unavailable",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=400, detail=f"{dependency_name} does not exist")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=503,
            detail=f"{dependency_name} service unavailable",
        )
    return response.json()


def publish_order_created(order: Order) -> bool:
    payload = {
        "event": "order.created",
        "orderId": order.id,
        "userId": order.user_id,
        "productId": order.product_id,
        "quantity": order.quantity,
        "total": str(order.total),
        "createdAt": order.created_at.isoformat(),
    }
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue="order-created", durable=True)
        channel.basic_publish(
            exchange="",
            routing_key="order-created",
            body=json.dumps(payload).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
            ),
        )
        connection.close()
        return True
    except Exception as exc:
        logger.error("order saved but notification could not be queued: %s", exc)
        return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialise_database()
    yield


app = FastAPI(title="ShopLite Order Service", version="1.0.0", lifespan=lifespan)
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
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("database readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> OrderRead:
    fetch_dependency(
        f"{USER_SERVICE_URL}/users/{payload.user_id}",
        "user",
    )
    product = fetch_dependency(
        f"{CATALOG_SERVICE_URL}/products/{payload.product_id}",
        "catalog",
    )

    unit_price = Decimal(str(product["price"])).quantize(Decimal("0.01"))
    order = Order(
        user_id=payload.user_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        unit_price=unit_price,
        total=unit_price * payload.quantity,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    order.notification_queued = publish_order_created(order)
    db.commit()
    db.refresh(order)
    logger.info(
        "created order id=%s notification_queued=%s",
        order.id,
        order.notification_queued,
    )
    return OrderRead.model_validate(order)


@router.get("/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)
