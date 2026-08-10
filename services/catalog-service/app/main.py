from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("catalog-service")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shoplite_catalog")

client: MongoClient[dict[str, Any]] = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=1500,
    connectTimeoutMS=1500,
)
database = client[MONGO_DB_NAME]
products: Collection[dict[str, Any]] = database["products"]


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    price: float = Field(gt=0, le=1_000_000)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProductRead(BaseModel):
    id: str
    name: str
    price: float
    attributes: dict[str, Any]


def serialise_product(document: dict[str, Any]) -> ProductRead:
    return ProductRead(
        id=str(document["_id"]),
        name=document["name"],
        price=float(document["price"]),
        attributes=document.get("attributes", {}),
    )


def initialise_database(max_attempts: int = 12, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            client.admin.command("ping")
            products.create_index([("name", ASCENDING)])
            logger.info("database ready")
            return
        except Exception:
            logger.warning("database not ready (attempt %s/%s)", attempt, max_attempts)
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialise_database()
    yield
    client.close()


app = FastAPI(title="ShopLite Catalog Service", version="1.0.0", lifespan=lifespan)
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
        client.admin.command("ping")
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("database readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@router.post(
    "/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED
)
def create_product(payload: ProductCreate) -> ProductRead:
    document = {
        "name": payload.name.strip(),
        "price": round(payload.price, 2),
        "attributes": payload.attributes,
    }
    result = products.insert_one(document)
    document["_id"] = result.inserted_id
    logger.info("created product id=%s", result.inserted_id)
    return serialise_product(document)


@router.get("/products", response_model=list[ProductRead])
def list_products(limit: int = Query(default=50, ge=1, le=100)) -> list[ProductRead]:
    return [serialise_product(document) for document in products.find().limit(limit)]


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: str) -> ProductRead:
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail="product not found")
    document = products.find_one({"_id": ObjectId(product_id)})
    if document is None:
        raise HTTPException(status_code=404, detail="product not found")
    return serialise_product(document)


app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)
