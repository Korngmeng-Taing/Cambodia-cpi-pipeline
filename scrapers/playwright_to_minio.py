"""
scrapers/playwright_to_minio.py
───────────────────────────────
Playwright-based e-commerce scraper that persists a daily "full state" snapshot
of a website's products to a MinIO (S3-compatible) bucket as a Snappy-compressed
Parquet file.

Pipeline stages (adheres to the Bronze layer contract):
    1. scrape()          – launch Chromium via Playwright, navigate, extract products
    2. build_bronze_frame – wrap extracted records in a pandas DataFrame and inject
                            the metadata columns scrape_batch_id, scrape_timestamp,
                            source_name
    3. write_snappy_parquet – persist the DataFrame locally with pyarrow (snappy)
    4. upload_to_minio    – upload the Parquet file with boto3 under
                            source={source_name}/scrape_date={YYYY-MM-DD}/{batch_id}.parquet

Object layout in the bucket (one object per daily snapshot):
    s3://cpi-bronze/source={source_name}/scrape_date={YYYY-MM-DD}/{scrape_batch_id}.parquet

A scrape returns the FULL state of the site (every current product), so downstream
Silver deduplication keeps exactly one price per canonical item per day.

Requirements: playwright, pandas, pyarrow, boto3
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError
from playwright.sync_api import Browser, Page, sync_playwright

log = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "cpi-bronze")

# Required extracted fields from the website's full-state snapshot.
REQUIRED_FIELDS = (
    "raw_item_id",
    "raw_product_name",
    "raw_price",
    "raw_currency",
    "raw_unit_size",
    "is_promotional",
    "source_url",
)


class GenericPlaywrightScraper:
    """
    Generic full-state product scraper driven by CSS selectors.

    Subclass or reuse this with a selector map; the example `supermarket_a`
    demo below shows a minimal end-to-end usage.
    """

    def __init__(
        self,
        source_name: str,
        start_url: str,
        item_selector: str = "body",
        field_selectors: dict[str, str] | None = None,
        wait_for_selector: str | None = None,
        headless: bool = True,
    ):
        self.source_name = source_name
        self.start_url = start_url
        self.item_selector = item_selector
        self.field_selectors = field_selectors or {}
        self.wait_for_selector = wait_for_selector
        self.headless = headless

    def _extract_item(self, item) -> dict[str, Any]:
        """Extracts one product card. Override for site-specific logic."""
        record: dict[str, Any] = {
            "raw_item_id": item.get_attribute("data-item-id") or "",
            "raw_product_name": item.inner_text().strip()[:200],
            "raw_price": 0.0,
            "raw_currency": "USD",
            "raw_unit_size": "",
            "is_promotional": False,
            "source_url": self.start_url,
        }
        for field, selector in self.field_selectors.items():
            if field not in record:
                node = item.query_selector(selector)
                if node:
                    record[field] = node.inner_text().strip()
        return record

    def scrape(self, page: Page) -> list[dict[str, Any]]:
        """Scrapes the FULL state of the site: every current product card."""
        page.goto(self.start_url, wait_until="networkidle", timeout=60_000)
        if self.wait_for_selector:
            page.wait_for_selector(self.wait_for_selector, timeout=30_000)
        items = page.query_selector_all(self.item_selector)
        records = [self._extract_item(item) for item in items]
        log.info("Extracted %d raw items from %s", len(records), self.source_name)
        return records


def scrape_full_state(
    scraper: GenericPlaywrightScraper,
    browser_type: str = "chromium",
    headless: bool | None = None,
) -> list[dict[str, Any]]:
    """Launches Playwright, runs the scraper against the live site, closes the browser."""
    if headless is None:
        headless = scraper.headless
    with sync_playwright() as p:
        browser: Browser = getattr(p, browser_type).launch(headless=headless)
        page = browser.new_page()
        try:
            return scraper.scrape(page)
        finally:
            browser.close()


def build_bronze_frame(
    records: list[dict[str, Any]],
    source_name: str,
    batch_id: uuid.UUID | None = None,
    scrape_timestamp: datetime | None = None,
) -> pd.DataFrame:
    """
    Converts the extracted list of dicts into a pandas DataFrame and injects the
    Bronze metadata columns:
        scrape_batch_id   – UUID4 for the snapshot batch
        scrape_timestamp  – UTC datetime when the snapshot was taken
        source_name       – e.g. 'supermarket_a'
    """
    if not records:
        raise ValueError(
            f"Scraper for '{source_name}' returned 0 products (full-state gate)."
        )

    batch_id = batch_id or uuid.uuid4()
    timestamp = scrape_timestamp or datetime.now(UTC)
    scrape_date = timestamp.date().isoformat()

    normalized: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rec = {k: rec.get(k) for k in REQUIRED_FIELDS}
        try:
            rec["raw_price"] = float(rec["raw_price"])
        except (TypeError, ValueError):
            log.warning(
                "Dropping item %r: raw_price not numeric: %r",
                rec.get("raw_item_id"),
                rec.get("raw_price"),
            )
            continue
        rec["is_promotional"] = bool(rec["is_promotional"])
        rec["scrape_batch_id"] = str(batch_id)
        rec["scrape_timestamp"] = timestamp
        rec["scrape_date"] = scrape_date
        rec["source_name"] = source_name
        normalized.append(rec)

    if not normalized:
        raise ValueError(
            f"Scraper for '{source_name}' produced 0 valid records after normalization."
        )

    df = pd.DataFrame(
        normalized,
        columns=[
            *REQUIRED_FIELDS,
            "scrape_batch_id",
            "scrape_timestamp",
            "scrape_date",
            "source_name",
        ],
    )
    df["is_promotional"] = df["is_promotional"].astype(bool)
    df["scrape_batch_id"] = df["scrape_batch_id"].astype(str)
    df["source_name"] = df["source_name"].astype(str)
    log.info("Built bronze frame for '%s': %d rows", source_name, len(df))
    return df


def write_snappy_parquet(df: pd.DataFrame, target_dir: str | Path) -> Path:
    """Persists a pandas DataFrame to a Snappy-compressed Parquet file."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / f"{df['scrape_batch_id'].iloc[0]}.parquet"
    df.to_parquet(out_file, engine="pyarrow", compression="snappy", index=False)
    log.info("Wrote Snappy Parquet (%d rows) -> %s", len(df), out_file)
    return out_file


def get_s3_client() -> boto3.client:
    """
    Builds a boto3 S3 client configured for MinIO, transparently falling back from
    the docker-internal hostname (minio:9000) to localhost when running on the host.
    """
    endpoint = MINIO_ENDPOINT
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3},
            ),
            region_name="us-east-1",
        )
        client.list_buckets()
        return client
    except Exception as exc:
        if "minio" not in endpoint:
            raise
        alt = endpoint.replace("minio:9000", "localhost:9000")
        log.warning("MinIO unreachable at %s (%s); retrying %s", endpoint, exc, alt)
        client = boto3.client(
            "s3",
            endpoint_url=alt,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3},
            ),
            region_name="us-east-1",
        )
        client.list_buckets()
        return client


def ensure_bucket(client: boto3.client, bucket: str = MINIO_BUCKET) -> None:
    """Creates the bucket if it does not already exist."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=bucket)
            log.info("Created MinIO bucket: %s", bucket)
        except ClientError as exc:
            log.warning("Could not create bucket %s: %s", bucket, exc)


def upload_to_minio(
    local_file: str | Path,
    source_name: str,
    scrape_date: str,
    batch_id: uuid.UUID,
) -> str:
    """
    Uploads a local Parquet file to MinIO under:
        source={source_name}/scrape_date={YYYY-MM-DD}/{scrape_batch_id}.parquet

    Returns the S3 object key.
    """
    local_file = Path(local_file)
    if not local_file.exists():
        raise FileNotFoundError(f"Parquet file not found: {local_file}")

    s3_key = f"source={source_name}/scrape_date={scrape_date}/{batch_id}.parquet"
    client = get_s3_client()
    ensure_bucket(client)
    client.upload_file(
        str(local_file),
        MINIO_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": "application/vnd.apache.parquet"},
    )
    log.info("Uploaded %s -> s3://%s/%s", local_file.name, MINIO_BUCKET, s3_key)
    return s3_key


def run(
    source_name: str,
    start_url: str,
    scraper_factory: Callable[[], GenericPlaywrightScraper] | None = None,
    out_dir: str | Path = "data/parquet_snapshots",
    scrape_date: str | None = None,
) -> dict[str, Any]:
    """
    End-to-end pipeline for one source:
        scrape (full state) → bronze frame → snappy parquet → MinIO upload

    Returns a summary dict (source_name, batch_id, record_count, s3_key, ...).
    """
    scraper = (
        scraper_factory()
        if scraper_factory
        else GenericPlaywrightScraper(
            source_name=source_name,
            start_url=start_url,
            item_selector=os.getenv("PLAYWRIGHT_ITEM_SELECTOR", "body"),
            wait_for_selector=os.getenv("PLAYWRIGHT_WAIT_SELECTOR"),
            headless=os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0",
        )
    )

    batch_id = uuid.uuid4()
    timestamp = datetime.now(UTC)
    date_str = scrape_date or timestamp.date().isoformat()

    records = scrape_full_state(scraper)
    df = build_bronze_frame(
        records, source_name, batch_id=batch_id, scrape_timestamp=timestamp
    )
    local_file = write_snappy_parquet(df, out_dir)
    s3_key = upload_to_minio(local_file, source_name, date_str, batch_id)

    return {
        "source_name": source_name,
        "batch_id": str(batch_id),
        "record_count": int(len(df)),
        "scrape_date": date_str,
        "local_file": str(local_file),
        "s3_key": s3_key,
    }


# -----------------------------------------------------------------------------
# Example concrete scraper + CLI entry point (python -m scrapers.playwright_to_minio)
# -----------------------------------------------------------------------------
class SupermarketAScraper(GenericPlaywrightScraper):
    """Demonstration full-state scraper for a fictional 'supermarket_a'."""

    def __init__(self, start_url: str):
        super().__init__(
            source_name="supermarket_a",
            start_url=start_url,
            item_selector="div.product-card",
            field_selectors={
                "raw_product_name": ".product-name",
                "raw_price": ".product-price",
                "raw_currency": ".product-currency",
                "raw_unit_size": ".product-unit",
                "is_promotional": ".product-badge-promo",
            },
            wait_for_selector="div.product-card",
        )

    def _extract_item(self, item) -> dict[str, Any]:
        record = {
            "raw_item_id": item.get_attribute("data-item-id") or "",
            "raw_product_name": item.query_selector(".product-name")
            .inner_text()
            .strip(),
            "raw_price": (
                item.query_selector(".product-price").inner_text().replace(",", "")
                or "0"
            ),
            "raw_currency": (
                item.query_selector(".product-currency").inner_text().strip() or "USD"
            ),
            "raw_unit_size": (
                item.query_selector(".product-unit").inner_text().strip()
                if item.query_selector(".product-unit")
                else ""
            ),
            "is_promotional": bool(item.query_selector(".product-badge-promo")),
            "source_url": self.start_url,
        }
        return record


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    source = sys.argv[1] if len(sys.argv) > 1 else "supermarket_a"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    factory = (lambda: SupermarketAScraper(url)) if source == "supermarket_a" else None
    summary = run(source_name=source, start_url=url, scraper_factory=factory)
    print(summary)
