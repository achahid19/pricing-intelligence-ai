from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    min_price: Optional[Decimal] = Field(default=None, gt=0)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = Field(default=None, max_length=5000)
    sku: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=100)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    min_price: Optional[Decimal] = Field(default=None, gt=0)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = Field(default=None, max_length=5000)
    sku: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=100)


class ProductOut(BaseModel):
    id: int
    name: str
    price: Decimal
    currency: str
    min_price: Optional[Decimal]
    image_url: Optional[str]
    description: Optional[str]
    sku: Optional[str]
    brand: Optional[str]
    category: Optional[str]
    barcode: Optional[str]
    import_source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportResultOut(BaseModel):
    created: int
    skipped: list[str] = []
    errors: list[str] = []


class AiDescribeOut(BaseModel):
    title: str
    description: str
    category: Optional[str] = None
    image_url: str
