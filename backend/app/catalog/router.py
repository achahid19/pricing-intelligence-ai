import asyncio
import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.catalog import service as catalog_service
from app.catalog.models import Product, ProductSnapshot
from app.catalog.schemas import (
    AiDescribeOut,
    BulkDeleteResultOut,
    ImportResultOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    WebsiteImportCandidate,
    WebsiteImportConfirmIn,
    WebsiteImportDiscoverIn,
    WebsiteImportDiscoverOut,
)
from app.db.database import get_db
from app.discovery import service as discovery_service
from app.services import ai_client, url_check
from app.services.storage import save_image
from app.services.text import normalize_domain, normalize_product_name, strip_citations
from app.workspace.models import Workspace

logger = logging.getLogger(__name__)

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
    background_tasks: BackgroundTasks,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    return await catalog_service.create_product(db, background_tasks, workspace, payload)


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
    updates = payload.model_dump(exclude_unset=True)
    old_price = product.price
    for field, value in updates.items():
        setattr(product, field, value)
    # A source_url the user just typed in by hand is trusted outright — no
    # AI guess to doubt, they presumably checked it themselves. Clearing it
    # back to empty resets the flag too, since there's nothing to verify.
    if "source_url" in updates:
        product.source_url_verified = True if product.source_url else None
    # Only when price actually changed — never a snapshot for a save that
    # only touched description/category/etc, and never a duplicate row
    # for re-saving the same price unchanged.
    #
    # Built directly (not via product.snapshots.append(...)) and on
    # purpose: `product` here was loaded from the DB via db.get(), so its
    # `.snapshots` collection is lazy — touching it outside an explicit
    # await raises MissingGreenlet under the async engine. create_product/
    # import_products can use .append() safely because those `Product`
    # instances are brand new and transient (never loaded), so the
    # collection starts as an empty in-memory list with nothing to fetch.
    # Both sides can now be None (a website-imported product may not have
    # had a price yet) — only snapshot when there's an actual new price and
    # it's genuinely different from before, including the None -> real
    # price transition, which is itself a real, worth-recording price event.
    if "price" in updates and product.price is not None and (old_price is None or float(product.price) != float(old_price)):
        db.add(ProductSnapshot(workspace_id=workspace.id, product_id=product.id, price=product.price))
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


@router.delete("", response_model=BulkDeleteResultOut)
async def delete_all_products(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Delete every product in this workspace's catalog in one call.
    Cascades at the DB level (ondelete="CASCADE") to ProductSnapshot and
    any ProductMatch rows against these products — see discovery/models.py.
    Irreversible with no undo in this app, so the frontend gates this
    behind a typed confirmation, not a single click."""
    result = await db.execute(delete(Product).where(Product.workspace_id == workspace.id))
    await db.commit()
    return BulkDeleteResultOut(deleted=result.rowcount)


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


# ── Website import ───────────────────────────────────────────────────────────


@router.post("/website-import/discover", response_model=WebsiteImportDiscoverOut)
async def discover_website_products(
    payload: WebsiteImportDiscoverIn,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Scan the workspace's own website for products to import into its
    catalog. Reuses ai_client.discover_competitor_products (the same AI
    native-web-search machinery already proven on competitor sites,
    relationship_type="own") rather than a separate scraping pipeline — a
    standalone scraper was tried here once before and reverted as too
    complex to maintain (see docs/PROGRESS.md). Discovery only — nothing is
    written to the catalog until /confirm."""
    raw_url = payload.url or workspace.website
    if not raw_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No website set. Add one in Settings, or enter a URL here.",
        )
    domain = normalize_domain(raw_url)

    try:
        result, _search_count = await ai_client.discover_competitor_products(
            db, workspace.id, domain, workspace.name, max_products=payload.max_products, relationship_type="own"
        )
    except ai_client.NoActiveProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        # The 502 detail below is deliberately truncated/generic for the
        # client — the full traceback only ever existed in memory otherwise,
        # making a real failure here undiagnosable after the fact (hit this
        # exact gap live: a user's website-import 502s couldn't be explained
        # after the fact because nothing was logged anywhere).
        logger.exception("website-import discovery failed for workspace %s, domain %s", workspace.id, domain)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI provider couldn't complete product discovery: {str(exc)[:300]}",
        )

    # So re-running discovery only surfaces genuinely new products — a name
    # already in the catalog would just be skipped as a duplicate at
    # /confirm anyway (same normalize_product_name check used there), so
    # filtering it out here means the review screen doesn't keep re-showing
    # products you already imported on an earlier run. normalize_product_
    # name (not a bare .lower()) because AI discovery output isn't
    # deterministic across runs — the exact same real product can come back
    # phrased "Rise" one run and "Rise (Hébergement Web Mutualisé – shared
    # hosting)" the next, confirmed live.
    existing_result = await db.execute(select(Product.name).where(Product.workspace_id == workspace.id))
    existing_names = {normalize_product_name(n) for n in existing_result.scalars().all()}

    candidates: list[WebsiteImportCandidate] = []
    no_price_count = 0
    already_imported_count = 0
    for candidate in result.get("products", [])[: payload.max_products]:
        title = (candidate.get("title") or "").strip()
        if not title:
            continue
        if normalize_product_name(title) in existing_names:
            already_imported_count += 1
            continue
        try:
            raw_price = candidate.get("price")
            price = Decimal(str(raw_price)).quantize(Decimal("0.01")) if raw_price is not None else None
        except (InvalidOperation, ValueError, TypeError):
            price = None
        if price is not None and price <= 0:
            price = None
        if price is None:
            # Not every site publishes a price (B2B, quote-based, brand
            # sites that route to retailers) — still shown, not dropped, so
            # the user can add their real/internal price on review. Only
            # /confirm actually requires one, since that's where this
            # becomes a real catalog Product.
            no_price_count += 1
        raw_url = (candidate.get("url") or "").strip()
        candidates.append(
            WebsiteImportCandidate(
                title=title,
                price=price,
                currency=candidate.get("currency"),
                url=raw_url or domain,
                description=strip_citations(candidate.get("description")),
                stock_status=candidate.get("stock_status"),
                additional_info=strip_citations(candidate.get("additional_info")),
                # Never trust a fallback-to-bare-domain URL as verified —
                # url_verified only means something when the model actually
                # gave a specific page (see ai_client._url_is_cited).
                url_verified=bool(candidate.get("url_verified")) if raw_url else False,
            )
        )

    # Citation-based verification (set above, from the AI provider's own
    # search tool) is the strongest signal but sparse in practice for this
    # JSON-only prompt — top it up with a real HTTP reachability check for
    # whatever it didn't already confirm, so "verified" ends up meaning
    # what a user actually cares about: this link won't 404.
    unverified = [c for c in candidates if not c.url_verified]
    if unverified:
        async with httpx.AsyncClient() as client:
            reachable = await asyncio.gather(*(url_check.url_is_reachable(client, c.url) for c in unverified))
        for candidate, is_reachable in zip(unverified, reachable):
            candidate.url_verified = is_reachable

    # Final override: a URL genuinely can't be one product's own specific
    # page if a different product also claims it — real observed behavior
    # when the AI can't find an individual page and falls back to one
    # generic listing page for several products, which still passes the
    # reachability check above (the page is real, just not specific).
    generic_urls = url_check.find_generic_urls([(c.url, c.title) for c in candidates])
    for candidate in candidates:
        if candidate.url in generic_urls:
            candidate.url_verified = False

    return WebsiteImportDiscoverOut(
        domain=domain,
        candidates=candidates,
        no_price_count=no_price_count,
        already_imported_count=already_imported_count,
    )


async def _fetch_og_image(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Best-effort: grab a product page's og:image/twitter:image meta tag,
    if present. Deliberately not a general scraper — no crawling, no AI
    fallback, just one lookup on a URL the AI product-discovery step
    already returned, only for candidates actually being imported (see
    confirm_website_import). Silently returns None on any failure
    (unreachable page, no such meta tag, JS-rendered content) — a missing
    image should never block an otherwise-valid import."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        resp = await client.get(url, headers=url_check.HEADERS, follow_redirects=True, timeout=url_check.TIMEOUT)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ("og:image", "twitter:image"):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            content = tag.get("content") if tag else None
            if content:
                return content.strip()
    except httpx.HTTPError:
        pass
    return None


@router.post("/website-import/confirm", response_model=ImportResultOut)
async def confirm_website_import(
    payload: WebsiteImportConfirmIn,
    background_tasks: BackgroundTasks,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Create products from the candidates the user reviewed and selected
    on the discover screen. Same duplicate-name skip logic as CSV import.
    A candidate with no price is still created — not every site publishes
    one (B2B, quote-based, brand sites), and Product.price is nullable for
    exactly this reason; the user can add a real price later via the normal
    edit flow. Also attempts one best-effort og:image/twitter:image fetch
    per candidate being created (see _fetch_og_image) — the AI discovery
    step itself can't supply an image (native web search returns text, not
    page HTML), so this is a small, targeted enrichment rather than leaving
    every website-imported product without a photo."""
    existing = await db.execute(select(Product).where(Product.workspace_id == workspace.id))
    # normalize_product_name (not a bare .lower()), same reasoning and same
    # helper as /discover's already_imported filter — kept consistent so a
    # product that /discover correctly hid as "already imported" can't then
    # somehow slip through here as a fresh duplicate via a direct /confirm
    # call with a differently-phrased title for the same real product.
    existing_names = {normalize_product_name(p.name) for p in existing.scalars().all()}

    # Only fetch images for candidates that will actually be created —
    # never spend a request on one about to be skipped as a duplicate.
    to_create = [c for c in payload.products if normalize_product_name(c.title) not in existing_names]
    image_by_url: dict[str, Optional[str]] = {}
    if to_create:
        async with httpx.AsyncClient() as client:
            fetched = await asyncio.gather(*(_fetch_og_image(client, c.url) for c in to_create))
        image_by_url = {c.url: image for c, image in zip(to_create, fetched)}

    created = 0
    skipped: list[str] = []
    for candidate in payload.products:
        name = candidate.title.strip()
        if normalize_product_name(name) in existing_names:
            skipped.append(f"{name}: a product with this name already exists")
            continue
        product = Product(
            workspace_id=workspace.id,
            name=name,
            price=candidate.price,
            currency=(candidate.currency or "USD").upper()[:3],
            description=candidate.description,
            image_url=image_by_url.get(candidate.url),
            import_source="website_ai",
            source_url=candidate.url,
            source_url_verified=candidate.url_verified,
        )
        if product.price is not None:
            product.snapshots.append(ProductSnapshot(workspace_id=workspace.id, price=product.price))
        db.add(product)
        existing_names.add(normalize_product_name(name))
        created += 1

    await db.commit()

    # Only when something new actually landed — a no-op import (every
    # candidate a duplicate) has nothing new to match, so running this
    # would just spend an AI call for a guaranteed empty result.
    if created > 0:
        background_tasks.add_task(discovery_service.refresh_matches_for_workspace, workspace.id)
        await catalog_service.maybe_start_onboarding_pipeline(db, background_tasks, workspace)

    return ImportResultOut(created=created, skipped=skipped, errors=[])


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
    background_tasks: BackgroundTasks,
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
        product.snapshots.append(ProductSnapshot(workspace_id=workspace.id, price=product.price))
        db.add(product)
        if sku:
            existing_skus.add(sku.lower())
        existing_names.add(name.lower())
        created += 1

    await db.commit()

    if created > 0:
        background_tasks.add_task(discovery_service.refresh_matches_for_workspace, workspace.id)
        await catalog_service.maybe_start_onboarding_pipeline(db, background_tasks, workspace)

    return ImportResultOut(created=created, skipped=skipped, errors=errors)
