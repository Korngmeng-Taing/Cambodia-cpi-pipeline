import logging
import uuid
import warnings
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch
from rapidfuzz import fuzz
import numpy as np

from pipeline.config import get_database_url
from pipeline.text_clean import clean_name_for_matching, is_size_compatible
from pipeline.vector_item_matcher import VectorItemMatcher, is_spec_compatible
from pipeline.hierarchical_classifier import HierarchicalCOICOPClassifier

log = logging.getLogger(__name__)


def is_valid_barcode(barcode: str | None) -> bool:
    """Validates that a barcode is a genuine product identifier (GTIN-8/12/13/14)
    and not a retailer placeholder, department dummy code, or sequence of identical digits."""
    if not barcode:
        return False
    b = str(barcode).strip()
    if not (4 <= len(b) <= 18 and b.isdigit()):
        return False
    if len(set(b)) <= 1:
        return False
    if b in {"123456789012", "1234567890123"}:
        return False
    if b.endswith("00000000"):
        return False
    return True


class ItemMatcher:
    use_vector_matcher: bool = True
    _has_embedding_column: bool = False

    def __init__(
        self,
        auto_accept_threshold: float = 0.95,
        review_threshold: float = 0.85,
        db_conn_str: str | None = None,
        use_vector_matcher: bool = True,
    ):
        psycopg2.extras.register_uuid()
        self.auto_accept_threshold = auto_accept_threshold
        self.review_threshold = review_threshold
        self.db_conn_str = db_conn_str or get_database_url()
        self.use_vector_matcher = use_vector_matcher
        self.barcode_cache: dict[str, uuid.UUID] = {}
        self.exact_name_cache: dict[str, uuid.UUID] = {}
        self.sku_cache: dict[tuple[str, str], uuid.UUID] = {}
        self.items_cache: list[tuple[uuid.UUID, str, str | None]] = []
        self._vector_matcher: VectorItemMatcher | None = None
        self._has_embedding_column: bool = False

    @property
    def vector_matcher(self) -> VectorItemMatcher:
        if self._vector_matcher is None:
            self._vector_matcher = VectorItemMatcher()
        return self._vector_matcher

    def _format_vector(self, text: str) -> str | None:
        """Generates unit-normalized pgvector string representation for a text."""
        try:
            vec = self.vector_matcher.embed_text(text)
            vnorm = np.linalg.norm(vec)
            vec_unit = (vec / vnorm).tolist() if vnorm > 0 else vec.tolist()
            return "[" + ",".join(str(round(float(x), 6)) for x in vec_unit) + "]"
        except Exception as e:
            log.debug("Vector formatting for '%s' skipped: %s", text, e)
            return None

    def _get_connection(self):
        from pipeline.config import alternate_host_url
        conn_str = self.db_conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
        try:
            conn = psycopg2.connect(conn_str)
        except psycopg2.OperationalError:
            conn = psycopg2.connect(alternate_host_url(conn_str))
        psycopg2.extras.register_uuid(conn_or_curs=conn)
        return conn

    def _load_cache(self, conn):
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_schema = 'silver' AND table_name = 'canonical_items' AND column_name = 'embedding'
                    );
                """)
                self._has_embedding_column = bool(cur.fetchone()[0])
            except Exception:
                self._has_embedding_column = False

            cur.execute(
                "SELECT item_id, canonical_name, barcode, size_norm FROM silver.canonical_items"
            )
            rows = cur.fetchall()
            self.barcode_cache.clear()
            self.exact_name_cache.clear()
            self.items_cache.clear()
            self.sku_cache.clear()
            for item_id, name, barcode, size_norm in rows:
                if barcode and is_valid_barcode(barcode):
                    self.barcode_cache[barcode.strip()] = item_id
                if name:
                    self.exact_name_cache[name.strip().upper()] = item_id
                self.items_cache.append((item_id, name, size_norm))

            try:
                cur.execute("SAVEPOINT load_sku_cache_sp")
                cur.execute(
                    "SELECT source_name, raw_item_id, canonical_item_id FROM silver.dim_canonical_products WHERE source_name IS NOT NULL AND raw_item_id IS NOT NULL"
                )
                for source_name, raw_item_id, canonical_item_id in cur.fetchall():
                    self.sku_cache[(source_name, raw_item_id.strip())] = canonical_item_id
                cur.execute("RELEASE SAVEPOINT load_sku_cache_sp")
            except Exception as e:
                log.warning(
                    "SKU cache load failed — SKU matching disabled for this run: %s. "
                    "Items will fall through to fuzzy/new_item matching.",
                    e,
                )
                try:
                    cur.execute("ROLLBACK TO SAVEPOINT load_sku_cache_sp")
                except Exception:
                    pass

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
        if not barcode or not is_valid_barcode(barcode):
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
                    cur.execute("SAVEPOINT match_sku_sp")
                    try:
                        cur.execute(
                            "SELECT canonical_item_id FROM silver.dim_canonical_products WHERE source_name = %s AND raw_item_id = %s",
                            (store_id, sku_clean),
                        )
                        res = cur.fetchone()
                        cur.execute("RELEASE SAVEPOINT match_sku_sp")
                        if res:
                            self.sku_cache[key] = res[0]
                            return res[0], 1.0
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT match_sku_sp")
            except Exception:
                pass
        return None

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
            if abs(target_len - cand_len) > max(target_len, cand_len) * 0.35:
                continue

            if not is_size_compatible(size_norm, cand_size):
                continue

            if not is_spec_compatible(name_clean, canonical_name):
                continue

            score = fuzz.token_sort_ratio(name_clean, canonical_name, score_cutoff=int(best_score * 100)) / 100.0
            if score > best_score:
                best_score = score
                best_match_id = item_id
                best_name = canonical_name

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
        store_slug: str = "",
    ) -> uuid.UUID:
        item_id = uuid.uuid4()
        
        # Auto-classify new canonical item into UN COICOP
        coicop_div, coicop_code = None, None
        try:
            classifier = HierarchicalCOICOPClassifier("coicop_hierarchy.json")
            res = classifier.classify_product(name, store_slug=store_slug)
            coicop_div = res.get("coicop_division")
            coicop_code = res.get("coicop_code")
        except Exception as e:
            log.warning("COICOP classification on create_canonical_item failed: %s", e)

        valid_bc = barcode if is_valid_barcode(barcode) else None
        vec_str = self._format_vector(name) if self._has_embedding_column else None

        with conn.cursor() as cur:
            if self._has_embedding_column and vec_str is not None:
                cur.execute(
                    """
                    INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm, coicop_division, coicop_code, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    (item_id, name, brand, valid_bc, size_norm, coicop_div, coicop_code, vec_str),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm, coicop_division, coicop_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    (item_id, name, brand, valid_bc, size_norm, coicop_div, coicop_code),
                )
        if valid_bc:
            self.barcode_cache[valid_bc.strip()] = item_id
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
        """Match a single record against the canonical item catalogue.

        .. deprecated::
            The production pipeline uses :meth:`process_unmatched_batch` which
            processes records in bulk with batched DB writes. This single-record
            method is retained for unit tests and one-off lookups only.
            Do NOT add new callers — use ``ItemMatcher().process_unmatched_batch()``
            instead.
        """
        warnings.warn(
            "ItemMatcher.match_record is deprecated; use process_unmatched_batch instead.",
            DeprecationWarning,
            stacklevel=2,
        )
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

        # 3. Exact Name match
        name_clean = clean_name_for_matching(item_description_raw)
        name_upper = name_clean.strip().upper() if name_clean else ""
        if name_upper and name_upper in self.exact_name_cache:
            item_id = self.exact_name_cache[name_upper]
            self._log_match(raw_price_id, item_id, "exact_text", 1.0, actual_conn)
            stats["matched_fuzzy"] += 1
            return stats

        # 4. Vector or Fuzzy text match with Spec Guard
        match = None
        matched_method = "fuzzy_text"
        if self.use_vector_matcher:
            try:
                vm = self.vector_matcher
                catalog = [{"item_id": iid, "canonical_name": cn} for iid, cn, _ in self.items_cache if cn]
                if catalog:
                    match_result = vm.match_candidate(name_clean, catalog)
                    item_id_match = match_result.get("matched_item_id") or match_result.get("item_id") if match_result else None
                    if item_id_match:
                        match = (item_id_match, match_result.get("confidence", 0.0), match_result.get("canonical_name", ""))
                        matched_method = "vector_embedding"
                else:
                    match = self.match_by_fuzzy_text(name_clean, size_norm, actual_conn)
                    matched_method = "fuzzy_text"
            except Exception as e:
                log.warning("Vector matcher failed, falling back to fuzzy text: %s", e)
                match = self.match_by_fuzzy_text(name_clean, size_norm, actual_conn)
                matched_method = "fuzzy_text"
        else:
            match = self.match_by_fuzzy_text(name_clean, size_norm, actual_conn)
            matched_method = "fuzzy_text"

        if match:
            item_id, conf, matched_name = match
            if conf >= self.auto_accept_threshold:
                self._log_match(raw_price_id, item_id, matched_method, conf, actual_conn)
                stats["matched_fuzzy"] += 1
                return stats
            elif conf >= self.review_threshold:
                self._send_to_review(
                    raw_price_id,
                    item_description_raw,
                    item_id,
                    matched_name,
                    conf,
                    actual_conn,
                )
                stats["sent_to_review"] += 1
                return stats

        # 5. Create new canonical item with auto-classification
        item_id = self.create_canonical_item(
            name_clean, actual_brand, barcode, size_norm, actual_conn, store_slug=store_id
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
                ON CONFLICT (raw_price_id) DO NOTHING
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

        catalog = [{"item_id": iid, "canonical_name": cn} for iid, cn, _ in self.items_cache if cn]
        classifier = None
        try:
            classifier = HierarchicalCOICOPClassifier("coicop_hierarchy.json")
        except Exception:
            classifier = None

        for row in rows:
            raw_price_id, desc, barcode, sku, store_id, brand, package_size = row
            name_clean = clean_name_for_matching(desc)

            # 1. Exact Barcode match
            if barcode and is_valid_barcode(barcode) and barcode.strip() in self.barcode_cache:
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
                match_logs.append((raw_price_id, str(item_id), "exact_text", 1.0))
                totals["matched_fuzzy"] += 1
                continue

            # 4. Vector or Fuzzy Text match
            match = None
            matched_method = "fuzzy_text"
            if self.use_vector_matcher:
                try:
                    vm = self.vector_matcher
                    match_result = None
                    if self._has_embedding_column:
                        try:
                            match_result = vm.match_candidate_db(name_clean, conn)
                        except Exception as e:
                            log.debug("pgvector native search failed, falling back to memory: %s", e)
                            match_result = None

                    if not match_result and catalog:
                        match_result = vm.match_candidate(name_clean, catalog)

                    item_id_match = match_result.get("matched_item_id") or match_result.get("item_id") if match_result else None
                    if item_id_match:
                        match = (item_id_match, match_result.get("confidence", 0.0), match_result.get("canonical_name", ""))
                        matched_method = "vector_embedding"
                    else:
                        match = self.match_by_fuzzy_text(name_clean, package_size)
                        matched_method = "fuzzy_text"
                except Exception as e:
                    log.warning("Vector matcher failed, falling back to fuzzy text: %s", e)
                    match = self.match_by_fuzzy_text(name_clean, package_size)
                    matched_method = "fuzzy_text"
            else:
                match = self.match_by_fuzzy_text(name_clean, package_size)
                matched_method = "fuzzy_text"

            if match:
                item_id, conf, matched_name = match
                if conf >= self.auto_accept_threshold:
                    match_logs.append((raw_price_id, str(item_id), matched_method, conf))
                    totals["matched_fuzzy"] += 1
                    continue
                elif conf >= self.review_threshold:
                    reviews.append(
                        (raw_price_id, desc, str(item_id), matched_name, conf)
                    )
                    totals["sent_to_review"] += 1
                    continue

            # 5. Create new canonical item with auto-classification
            new_id = uuid.uuid4()
            coicop_div, coicop_code = None, None
            try:
                if classifier is None:
                    classifier = HierarchicalCOICOPClassifier("coicop_hierarchy.json")
                res = classifier.classify_product(name_clean, store_slug=store_id)
                coicop_div = res.get("coicop_division")
                coicop_code = res.get("coicop_code")
            except Exception as e:
                log.warning("COICOP classification on batch new item failed: %s", e)

            vec_str = self._format_vector(name_clean) if self._has_embedding_column else None
            valid_bc = barcode if is_valid_barcode(barcode) else None
            if self._has_embedding_column:
                new_items.append((str(new_id), name_clean, brand, valid_bc, package_size, coicop_div, coicop_code, vec_str))
            else:
                new_items.append((str(new_id), name_clean, brand, valid_bc, package_size, coicop_div, coicop_code))

            if valid_bc:
                self.barcode_cache[valid_bc.strip()] = new_id
            if sku:
                sku_clean = sku.strip()
                self.sku_cache[(store_id, sku_clean)] = new_id
                sku_registrations.append(
                    (str(new_id), name_clean, store_id, sku_clean)
                )
            if name_upper:
                self.exact_name_cache[name_upper] = new_id
            self.items_cache.append((new_id, name_clean, package_size))
            catalog.append({"item_id": new_id, "canonical_name": name_clean})

            match_logs.append((raw_price_id, str(new_id), "new_item", 1.0))
            totals["new_items_created"] += 1

        with conn.cursor() as cur:
            if new_items:
                if self._has_embedding_column:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm, coicop_division, coicop_code, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                        ON CONFLICT (item_id) DO NOTHING
                        """,
                        new_items,
                        page_size=1000,
                    )
                else:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm, coicop_division, coicop_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                    ON CONFLICT (source_name, raw_item_id) DO NOTHING
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
                    ON CONFLICT (raw_price_id) DO NOTHING
                    """,
                    reviews,
                    page_size=1000,
                )
            conn.commit()

        return totals
