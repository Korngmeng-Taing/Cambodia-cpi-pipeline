import logging
import os
import re
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch
from rapidfuzz import fuzz

from pipeline.text_clean import clean_name_for_matching

log = logging.getLogger(__name__)


class ItemMatcher:
    def __init__(
        self,
        auto_accept_threshold: float = 0.95,
        review_threshold: float = 0.85,
        db_conn_str: str | None = None,
    ):
        psycopg2.extras.register_uuid()
        self.auto_accept_threshold = auto_accept_threshold
        self.review_threshold = review_threshold
        self.db_conn_str = db_conn_str or os.getenv(
            "CPI_DATABASE_URL",
            "postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db",
        )
        self.barcode_cache: dict[str, uuid.UUID] = {}
        self.exact_name_cache: dict[str, uuid.UUID] = {}
        self.sku_cache: dict[tuple[str, str], uuid.UUID] = {}
        self.items_cache: list[tuple[uuid.UUID, str, str | None]] = []

    def _get_connection(self):
        conn_str = self.db_conn_str.replace("postgresql+psycopg2://", "postgresql://")
        try:
            conn = psycopg2.connect(conn_str)
        except psycopg2.OperationalError:
            if "postgres" in conn_str:
                alt = conn_str.replace("postgres:5432", "localhost:5432")
            else:
                alt = conn_str.replace("localhost:5432", "postgres:5432")
            conn = psycopg2.connect(alt)
        psycopg2.extras.register_uuid(conn_or_curs=conn)
        return conn

    def _load_cache(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, canonical_name, barcode, size_norm FROM silver.canonical_items"
            )
            rows = cur.fetchall()
            self.barcode_cache.clear()
            self.exact_name_cache.clear()
            self.items_cache.clear()
            self.sku_cache.clear()
            for item_id, name, barcode, size_norm in rows:
                if barcode:
                    self.barcode_cache[barcode.strip()] = item_id
                if name:
                    self.exact_name_cache[name.strip().upper()] = item_id
                self.items_cache.append((item_id, name, size_norm))
            # SKU cache: process_batch() only consults the in-memory cache, so
            # without this preload every pre-existing SKU was invisible to the
            # batch path and fell through to fuzzy/new_item matching.
            cur.execute(
                "SELECT source_name, raw_item_id, canonical_item_id FROM silver.dim_canonical_products WHERE source_name IS NOT NULL AND raw_item_id IS NOT NULL"
            )
            for source_name, raw_item_id, canonical_item_id in cur.fetchall():
                self.sku_cache[(source_name, raw_item_id.strip())] = canonical_item_id

    def process_unmatched_batch(
        self,
        limit: int = 100000,
        batch_size: int = 1000,
        scrape_date: str | None = None,
    ) -> dict:
        conn = self._get_connection()
        try:
            return self.process_batch(
                conn, limit=limit, batch_size=batch_size, scrape_date=scrape_date
            )
        finally:
            conn.close()

    def match_by_barcode(
        self, barcode: str | None, conn: Any = None
    ) -> tuple[uuid.UUID, float] | None:
        if not barcode:
            return None
        barcode_clean = barcode.strip()
        if barcode_clean in self.barcode_cache:
            return self.barcode_cache[barcode_clean], 1.0
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT item_id FROM silver.canonical_items WHERE barcode = %s",
                    (barcode_clean,),
                )
                res = cur.fetchone()
                if res:
                    self.barcode_cache[barcode_clean] = res[0]
                    return res[0], 1.0
        return None

    def match_by_sku(
        self, store_id: str, sku: str | None, conn: Any = None
    ) -> tuple[uuid.UUID, float] | None:
        if not sku or not store_id:
            return None
        sku_clean = sku.strip()
        key = (store_id, sku_clean)
        if key in self.sku_cache:
            return self.sku_cache[key], 1.0
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT canonical_item_id FROM silver.dim_canonical_products WHERE source_name = %s AND raw_item_id = %s",
                        (store_id, sku_clean),
                    )
                    res = cur.fetchone()
                    if res:
                        self.sku_cache[key] = res[0]
                        return res[0], 1.0
            except Exception:
                pass
        return None

    @staticmethod
    def _is_size_compatible(
        size1: str | None, size2: str | None, tolerance: float = 0.10
    ) -> bool:
        """Check if two package sizes are compatible within a relative tolerance."""
        if not size1 or not size2:
            return True
        s1 = size1.strip().lower()
        s2 = size2.strip().lower()
        if s1 == s2:
            return True
        m1 = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)$", s1)
        m2 = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)$", s2)
        if m1 and m2:
            v1, u1 = float(m1.group(1)), m1.group(2)
            v2, u2 = float(m2.group(1)), m2.group(2)
            if v1 > 0 and v2 > 0:
                # Normalize equivalent units so e.g. "330ml" matches "0.33L"
                # (previously any unit mismatch rejected the candidate).
                factors = {"ml": 0.001, "l": 1.0, "g": 0.001, "kg": 1.0}
                f1, f2 = factors.get(u1), factors.get(u2)
                if (
                    f1 is not None
                    and f2 is not None
                    and (u1 in ("ml", "l")) == (u2 in ("ml", "l"))
                ):
                    b1, b2 = v1 * f1, v2 * f2
                    diff = abs(b1 - b2) / max(b1, b2)
                    return diff <= tolerance
                if u1 == u2:
                    diff = abs(v1 - v2) / max(v1, v2)
                    return diff <= tolerance
        return False

    def match_by_fuzzy_text(
        self, name_clean: str, size_norm: str | None, conn: Any = None
    ) -> tuple[uuid.UUID, float, str] | None:
        if not name_clean:
            return None
        name_clean_upper = name_clean.strip().upper()
        if name_clean_upper in self.exact_name_cache:
            return self.exact_name_cache[name_clean_upper], 1.0, name_clean_upper

        best_match_id = None
        best_score = 0.0
        best_name = ""

        candidates = self.items_cache
        if not candidates and conn is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT item_id, canonical_name, size_norm FROM silver.canonical_items"
                )
                rows = cur.fetchall()
                candidates = []
                for row in rows:
                    if len(row) >= 3:
                        candidates.append((row[0], row[1], row[2]))
                    else:
                        candidates.append((row[0], row[1], None))

        target_len = len(name_clean)
        for item_id, canonical_name, cand_size in candidates:
            if not canonical_name:
                continue
            cand_len = len(canonical_name)
            # Length filter: skip if strings differ in length by more than 35%
            if abs(target_len - cand_len) > max(target_len, cand_len) * 0.35:
                continue

            if not self._is_size_compatible(size_norm, cand_size):
                continue

            score = fuzz.token_sort_ratio(name_clean, canonical_name, score_cutoff=int(best_score * 100)) / 100.0
            if score > best_score:
                best_score = score
                best_match_id = item_id
                best_name = canonical_name
                if best_score >= 0.96:
                    break

        if best_match_id:
            return best_match_id, best_score, best_name
        return None

    def create_canonical_item(
        self,
        name: str,
        brand: str | None,
        barcode: str | None,
        size_norm: str | None,
        conn,
    ) -> uuid.UUID:
        item_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (item_id) DO NOTHING
                """,
                (item_id, name, brand, barcode, size_norm),
            )
        if barcode:
            self.barcode_cache[barcode.strip()] = item_id
        if name:
            self.exact_name_cache[name.strip().upper()] = item_id
        self.items_cache.append((item_id, name, size_norm))
        return item_id

    def match_record(
        self,
        raw_price_id: int,
        item_description_raw: str,
        barcode: str | None = None,
        sku: str | None = None,
        store_id: str = "store",
        conn: Any = None,
        brand: str | None = None,
        size_norm: str | None = None,
        brand_or_conn: Any = None,
    ) -> dict:
        actual_conn = conn
        actual_brand = brand
        if brand_or_conn is not None:
            if hasattr(brand_or_conn, "cursor"):
                actual_conn = brand_or_conn
            else:
                actual_brand = brand_or_conn
        if actual_conn is None and hasattr(brand, "cursor"):
            actual_conn = brand
            actual_brand = None

        stats = {
            "matched_exact": 0,
            "matched_fuzzy": 0,
            "sent_to_review": 0,
            "new_items_created": 0,
        }

        # 1. Barcode match
        match = self.match_by_barcode(barcode, actual_conn)
        if match:
            item_id, conf = match
            self._log_match(raw_price_id, item_id, "barcode_exact", conf, actual_conn)
            stats["matched_exact"] += 1
            return stats

        # 2. SKU match
        match = self.match_by_sku(store_id, sku, actual_conn)
        if match:
            item_id, conf = match
            self._log_match(raw_price_id, item_id, "sku_exact", conf, actual_conn)
            stats["matched_exact"] += 1
            return stats

        # 3. Fuzzy text match
        name_clean = clean_name_for_matching(item_description_raw)
        match = self.match_by_fuzzy_text(name_clean, size_norm, actual_conn)

        if match:
            item_id, conf, matched_name = match
            if conf >= self.auto_accept_threshold:
                self._log_match(raw_price_id, item_id, "fuzzy_text", conf, actual_conn)
                stats["matched_fuzzy"] += 1
                return stats

        # 4. Create new canonical item for all unmatched items
        item_id = self.create_canonical_item(
            name_clean, actual_brand, barcode, size_norm, actual_conn
        )
        self._log_match(raw_price_id, item_id, "new_item", 1.0, actual_conn)
        stats["new_items_created"] += 1
        return stats

    def _log_match(
        self,
        raw_price_id: int,
        item_id: uuid.UUID,
        method: str,
        confidence: float,
        conn,
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO silver.item_match_log (raw_price_id, item_id, match_method, confidence)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (raw_price_id) DO NOTHING
                """,
                (raw_price_id, item_id, method, confidence),
            )

    def _send_to_review(
        self,
        raw_price_id: int,
        raw_desc: str,
        item_id: uuid.UUID,
        best_name: str,
        confidence: float,
        conn,
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO silver.needs_review (raw_price_id, item_description_raw, best_match_item_id, best_match_name, confidence)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (raw_price_id, raw_desc, item_id, best_name, confidence),
            )

    def process_batch(
        self,
        conn,
        limit: int = 100000,
        batch_size: int = 1000,
        scrape_date: str | None = None,
    ) -> dict:
        totals = {
            "matched_exact": 0,
            "matched_fuzzy": 0,
            "sent_to_review": 0,
            "new_items_created": 0,
        }
        self._load_cache(conn)

        query = """
            SELECT rp.raw_price_id, rp.item_description_raw,
                   (rp.raw_payload->>'barcode')::text as barcode,
                   (rp.raw_payload->>'sku')::text as sku,
                   rp.store_id,
                   (rp.raw_payload->>'brand')::text as brand,
                   (rp.raw_payload->>'package_size')::text as package_size
            FROM bronze.raw_prices rp
            LEFT JOIN silver.item_match_log iml ON rp.raw_price_id = iml.raw_price_id
            WHERE iml.raw_price_id IS NULL
        """
        params: list[Any] = []
        if scrape_date:
            query += " AND rp.scraped_at::date = %s::date"
            params.append(scrape_date)

        query += " ORDER BY rp.raw_price_id LIMIT %s"
        params.append(limit)

        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        if not rows:
            return totals

        match_logs = []
        new_items = []
        reviews = []
        sku_registrations = []

        for row in rows:
            raw_price_id, desc, barcode, sku, store_id, brand, package_size = row
            name_clean = clean_name_for_matching(desc)

            # 1. Exact Barcode match
            if barcode and barcode.strip() in self.barcode_cache:
                item_id = self.barcode_cache[barcode.strip()]
                match_logs.append((raw_price_id, str(item_id), "barcode_exact", 1.0))
                totals["matched_exact"] += 1
                continue

            # 2. SKU match
            if sku and (store_id, sku.strip()) in self.sku_cache:
                item_id = self.sku_cache[(store_id, sku.strip())]
                match_logs.append((raw_price_id, str(item_id), "sku_exact", 1.0))
                totals["matched_exact"] += 1
                continue

            # 3. Exact Name match
            name_upper = name_clean.strip().upper() if name_clean else ""
            if name_upper and name_upper in self.exact_name_cache:
                item_id = self.exact_name_cache[name_upper]
                match_logs.append((raw_price_id, str(item_id), "fuzzy_text", 1.0))
                totals["matched_fuzzy"] += 1
                continue

            # 4. Fuzzy Text match
            match = self.match_by_fuzzy_text(name_clean, package_size)
            if match:
                item_id, conf, matched_name = match
                if conf >= self.auto_accept_threshold:
                    match_logs.append((raw_price_id, str(item_id), "fuzzy_text", conf))
                    totals["matched_fuzzy"] += 1
                    continue

            # 5. Create new canonical item (all other unmatched items)
            new_id = uuid.uuid4()
            new_items.append((str(new_id), name_clean, brand, barcode, package_size))
            if barcode:
                self.barcode_cache[barcode.strip()] = new_id
            if sku:
                sku_clean = sku.strip()
                self.sku_cache[(store_id, sku_clean)] = new_id
                sku_registrations.append(
                    (str(new_id), name_clean, store_id, sku_clean)
                )
            if name_upper:
                self.exact_name_cache[name_upper] = new_id
            self.items_cache.append((new_id, name_clean, package_size))

            match_logs.append((raw_price_id, str(new_id), "new_item", 1.0))
            totals["new_items_created"] += 1

        # Bulk write to PostgreSQL
        with conn.cursor() as cur:
            if new_items:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    new_items,
                    page_size=1000,
                )
            if sku_registrations:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.dim_canonical_products
                        (canonical_item_id, canonical_name, source_name, raw_item_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (canonical_item_id) DO NOTHING
                    """,
                    sku_registrations,
                    page_size=1000,
                )
            if match_logs:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.item_match_log (raw_price_id, item_id, match_method, confidence)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (raw_price_id) DO NOTHING
                    """,
                    match_logs,
                    page_size=1000,
                )
            if reviews:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.needs_review (raw_price_id, item_description_raw, best_match_item_id, best_match_name, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    reviews,
                    page_size=1000,
                )
            conn.commit()

        return totals
