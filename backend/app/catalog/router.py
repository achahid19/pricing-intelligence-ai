import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.catalog.schemas import AiDescribeOut, ImportResultOut, ProductCreate, ProductOut, ProductUpdate
from app.db.database import get_db
from app.services import ai_client
from app.services.storage import save_image
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


# ── AI-assisted manual entry ────────────────────────────────────────────────


@router.post("/ai-describe", response_model=AiDescribeOut)
async def ai_describe_product(
    file: UploadFile,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Given a product photo, save it and ask the workspace's active AI
    provider for a suggested title, description, and category. Returns
    suggestions only — the caller (manual Add Product form) still requires
    the user to review and submit them; nothing is written to the catalog
    here."""
    image_url, image_bytes = await save_image(file)
    try:
        result = await ai_client.describe_product_image(
            db, workspace.id, image_bytes, file.content_type or "image/jpeg"
        )
    except ai_client.NoActiveProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider couldn't generate a description for this image. Try again or enter details manually.",
        )
    return AiDescribeOut(
        title=result.get("title", ""),
        description=result.get("description", ""),
        category=result.get("category") or None,
        image_url=image_url,
    )


# ── CSV/XLSX import ─────────────────────────────────────────────────────────

# Header aliases accepted in import files (case-insensitive) — mirrors the
# pattern from ai_crafters_pfa's products.py import, adapted for this schema.
_HEADER_MAP = {
    "name": "name", "product": "name", "product name": "name", "nom": "name",
    "sku": "sku", "reference": "sku", "ref": "sku",
    "price": "price", "your price": "price", "prix": "price",
    "min_price": "min_price", "minimum price": "min_price", "min price": "min_price",
    "map": "min_price", "map price": "min_price", "prix map": "min_price",
    "currency": "currency", "devise": "currency",
    "category": "category", "catégorie": "category", "categorie": "category",
    "brand": "brand", "marque": "brand",
    "barcode": "barcode", "code_barre": "barcode", "gtin": "barcode",
    "description": "description",
}

# Canonical column order for the downloadable template — mirrors the
# required/optional split documented on import_products() below.
_TEMPLATE_HEADERS = ["name", "price", "min_price", "currency", "sku", "category", "brand", "barcode", "description"]


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


@router.get("/import/template")
async def download_import_template():
    """A blank CSV with the exact column headers import_products() accepts,
    so users don't have to guess or reverse-engineer them from an error."""
    buffer = io.StringIO()
    csv.writer(buffer).writerow(_TEMPLATE_HEADERS)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="product_import_template.csv"'},
    )


@router.post("/import", response_model=ImportResultOut)
async def import_products(
    file: UploadFile,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-create products from a CSV or Excel file. Columns: name, price
    (required); sku, min_price (MAP floor), currency, category, brand,
    barcode, description (optional). Existing SKUs/names in this workspace
    are skipped, never overwritten."""
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

        # Optional — unlike price, a malformed min_price shouldn't fail the
        # whole row, since it's a bonus MAP-compliance field, not required
        # for the product to exist at all.
        min_price = None
        raw_min_price = (row.get("min_price") or "").replace(" ", "")
        if raw_min_price:
            if "," in raw_min_price and "." not in raw_min_price:
                raw_min_price = raw_min_price.replace(",", ".")
            try:
                parsed_min_price = Decimal(raw_min_price)
                if parsed_min_price > 0:
                    min_price = parsed_min_price.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                pass

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
            min_price=min_price,
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
