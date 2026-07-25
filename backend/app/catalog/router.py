import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.catalog.schemas import ImportResultOut, ProductCreate, ProductOut, ProductUpdate
from app.db.database import get_db
from app.workspace.models import Workspace

router = APIRouter()


@router.get("", response_model=list[ProductOut])
async def list_products(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.workspace_id == workspace.id).order_by(Product.name)
    )
    return result.scalars().all()


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    product = Product(workspace_id=workspace.id, import_source="manual", **payload.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or product.workspace_id != workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or product.workspace_id != workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or product.workspace_id != workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    await db.delete(product)
    await db.commit()


# ── CSV/XLSX import ─────────────────────────────────────────────────────────

# Header aliases accepted in import files (case-insensitive) — mirrors the
# pattern from ai_crafters_pfa's products.py import, adapted for this schema.
_HEADER_MAP = {
    "name": "name", "product": "name", "product name": "name", "nom": "name",
    "sku": "sku", "reference": "sku", "ref": "sku",
    "price": "price", "your price": "price", "prix": "price",
    "currency": "currency", "devise": "currency",
    "category": "category", "catégorie": "category", "categorie": "category",
    "brand": "brand", "marque": "brand",
    "barcode": "barcode", "code_barre": "barcode", "gtin": "barcode",
    "description": "description",
}


def _parse_import_rows(filename: str, content: bytes) -> list[dict]:
    """Yield normalized field dicts from a csv or xlsx file."""
    rows: list[dict] = []
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        header: Optional[list[Optional[str]]] = None
        for raw in ws.iter_rows(values_only=True):
            if header is None:
                header = [
                    _HEADER_MAP.get(str(c).strip().lower()) if c is not None else None
                    for c in raw
                ]
                continue
            row = {}
            for key, val in zip(header, raw):
                if key and val is not None:
                    row[key] = str(val).strip()
            if row:
                rows.append(row)
    else:
        text = content.decode("utf-8-sig", errors="replace")
        delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        for raw_row in reader:
            row = {}
            for key, val in raw_row.items():
                mapped = _HEADER_MAP.get((key or "").strip().lower())
                if mapped and val and val.strip():
                    row[mapped] = val.strip()
            if row:
                rows.append(row)
    return rows


@router.post("/import", response_model=ImportResultOut)
async def import_products(
    file: UploadFile,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-create products from a CSV or Excel file. Columns: name, price
    (required); sku, currency, category, brand, barcode, description
    (optional). Existing SKUs/names in this workspace are skipped, never
    overwritten."""
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")
    try:
        rows = _parse_import_rows(file.filename or "upload.csv", content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found — check the column headers")
    if len(rows) > 1000:
        raise HTTPException(status_code=413, detail="Too many rows (max 1000 per import)")

    existing = await db.execute(select(Product).where(Product.workspace_id == workspace.id))
    existing_products = existing.scalars().all()
    existing_skus = {p.sku.lower() for p in existing_products if p.sku}
    existing_names = {p.name.lower() for p in existing_products}

    created = 0
    skipped: list[str] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = row.get("name", "")
        if not name:
            errors.append(f"Row {i}: missing name")
            continue
        raw_price = row.get("price", "").replace(" ", "")
        if "," in raw_price and "." not in raw_price:
            raw_price = raw_price.replace(",", ".")
        try:
            price = Decimal(raw_price)
        except (InvalidOperation, ValueError):
            errors.append(f"Row {i} ({name}): invalid price '{row.get('price', '')}'")
            continue
        if price <= 0:
            errors.append(f"Row {i} ({name}): price must be positive")
            continue

        sku = row.get("sku") or None
        if sku and sku.lower() in existing_skus:
            skipped.append(f"{name}: SKU '{sku}' already exists")
            continue
        if name.lower() in existing_names:
            skipped.append(f"{name}: a product with this name already exists")
            continue

        product = Product(
            workspace_id=workspace.id,
            name=name,
            price=price.quantize(Decimal("0.01")),
            currency=(row.get("currency") or "USD").upper()[:3],
            sku=sku,
            category=row.get("category") or None,
            brand=row.get("brand") or None,
            barcode=row.get("barcode") or None,
            description=row.get("description") or None,
            import_source="csv",
        )
        db.add(product)
        if sku:
            existing_skus.add(sku.lower())
        existing_names.add(name.lower())
        created += 1

    await db.commit()
    return ImportResultOut(created=created, skipped=skipped, errors=errors)
