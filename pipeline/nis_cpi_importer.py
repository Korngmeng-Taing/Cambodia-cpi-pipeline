"""
pipeline/nis_cpi_importer.py
─────────────────────────────
Automated Ground-Truth Benchmark Ingestion Service for Official NIS Monthly CPI Releases.

Ingests official monthly headline & core CPI numbers published by the National
Institute of Statistics (NIS) / Ministry of Planning of Cambodia:
  1. Upserts into `gold.dim_nis_official_cpi` database table.
  2. Synchronizes `dbt/seeds/nis_official_cpi.csv` so dbt models and git repositories
     maintain an authoritative, version-controlled ground-truth record.
  3. Provides automated portal scraping and CLI manual entrypoint.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
from datetime import date, datetime
from typing import Any

from pipeline.config import get_db_connection

log = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_FILE = os.path.join(REPO_ROOT, "dbt", "seeds", "nis_official_cpi.csv")


class NISBenchmarkImporter:
    """Service to ingest and synchronize official NIS monthly CPI records."""

    def __init__(self, seed_file_path: str = SEED_FILE):
        self.seed_file_path = seed_file_path

    def ingest_record(
        self,
        cpi_month: str | date,
        headline_cpi: float,
        core_cpi: float | None = None,
        mom_inflation_pct: float | None = None,
        yoy_inflation_pct: float | None = None,
        division_indices: dict[str, float] | None = None,
        release_date: str | date | None = None,
        source_notes: str = "NIS Cambodia Official CPI Report",
        sync_seed: bool = True,
        conn: Any = None,
    ) -> dict[str, Any]:
        """Upserts an official monthly CPI benchmark into gold.dim_nis_official_cpi.

        Args:
            cpi_month: First day of the target month (e.g. '2026-08-01' or date(2026, 8, 1)).
            headline_cpi: Official headline index number.
            core_cpi: Official core index number (optional).
            mom_inflation_pct: Month-over-Month inflation % (optional).
            yoy_inflation_pct: Year-over-Year inflation % (optional).
            division_indices: Dict mapping '01' through '12' to division index numbers (optional).
            release_date: Official publication date (optional).
            source_notes: Provenance note or report title.
            sync_seed: Whether to update dbt/seeds/nis_official_cpi.csv.
            conn: Optional existing DB connection.

        Returns:
            dict containing status and record details.
        """
        # Normalize date types
        if isinstance(cpi_month, str):
            cpi_month_clean = cpi_month.strip()
            if len(cpi_month_clean) == 7 and re.match(r"^\d{4}-\d{2}$", cpi_month_clean):
                cpi_month_clean += "-01"
            cpi_month_dt = datetime.strptime(cpi_month_clean, "%Y-%m-%d").date()
        else:
            cpi_month_dt = cpi_month

        # Coerce first day of the month
        cpi_month_dt = cpi_month_dt.replace(day=1)

        if isinstance(release_date, str):
            release_date_dt = datetime.strptime(release_date.strip(), "%Y-%m-%d").date()
        elif isinstance(release_date, (date, datetime)):
            release_date_dt = release_date
        else:
            release_date_dt = None

        record: dict[str, Any] = {
            "cpi_month": cpi_month_dt.isoformat(),
            "headline_cpi": float(headline_cpi),
            "core_cpi": float(core_cpi) if core_cpi is not None else None,
            "mom_inflation_pct": float(mom_inflation_pct) if mom_inflation_pct is not None else None,
            "yoy_inflation_pct": float(yoy_inflation_pct) if yoy_inflation_pct is not None else None,
            "release_date": release_date_dt.isoformat() if release_date_dt else None,
            "source_notes": source_notes,
        }

        # Populate division fields cpi_division_01 through cpi_division_12
        div_dict = division_indices or {}
        for d in range(1, 13):
            d_key = f"{d:02d}"
            col_name = f"cpi_division_{d_key}"
            val = div_dict.get(d_key)
            record[col_name] = float(val) if val is not None else None

        # 1. Update Database
        should_close = False
        if conn is None:
            try:
                conn = get_db_connection()
                should_close = True
            except Exception as db_err:
                log.warning("Database connection unavailable (%s). Ingesting to seed only.", db_err)
                conn = None

        db_status = "skipped"
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS gold;")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS gold.dim_nis_official_cpi (
                            cpi_month DATE NOT NULL PRIMARY KEY,
                            headline_cpi NUMERIC(10, 4) NOT NULL,
                            core_cpi NUMERIC(10, 4),
                            mom_inflation_pct NUMERIC(8, 4),
                            yoy_inflation_pct NUMERIC(8, 4),
                            cpi_division_01 NUMERIC(10, 4),
                            cpi_division_02 NUMERIC(10, 4),
                            cpi_division_03 NUMERIC(10, 4),
                            cpi_division_04 NUMERIC(10, 4),
                            cpi_division_05 NUMERIC(10, 4),
                            cpi_division_06 NUMERIC(10, 4),
                            cpi_division_07 NUMERIC(10, 4),
                            cpi_division_08 NUMERIC(10, 4),
                            cpi_division_09 NUMERIC(10, 4),
                            cpi_division_10 NUMERIC(10, 4),
                            cpi_division_11 NUMERIC(10, 4),
                            cpi_division_12 NUMERIC(10, 4),
                            release_date DATE,
                            source_notes TEXT DEFAULT 'NIS Cambodia Official CPI Release',
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        );
                        """
                    )
                    # Alter table to add division columns if already created earlier
                    for d in range(1, 13):
                        cur.execute(f"ALTER TABLE gold.dim_nis_official_cpi ADD COLUMN IF NOT EXISTS cpi_division_{d:02d} NUMERIC(10, 4);")

                    cur.execute(
                        """
                        INSERT INTO gold.dim_nis_official_cpi (
                            cpi_month, headline_cpi, core_cpi, mom_inflation_pct,
                            yoy_inflation_pct,
                            cpi_division_01, cpi_division_02, cpi_division_03, cpi_division_04,
                            cpi_division_05, cpi_division_06, cpi_division_07, cpi_division_08,
                            cpi_division_09, cpi_division_10, cpi_division_11, cpi_division_12,
                            release_date, source_notes
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (cpi_month) DO UPDATE SET
                            headline_cpi = EXCLUDED.headline_cpi,
                            core_cpi = COALESCE(EXCLUDED.core_cpi, gold.dim_nis_official_cpi.core_cpi),
                            mom_inflation_pct = COALESCE(EXCLUDED.mom_inflation_pct, gold.dim_nis_official_cpi.mom_inflation_pct),
                            yoy_inflation_pct = COALESCE(EXCLUDED.yoy_inflation_pct, gold.dim_nis_official_cpi.yoy_inflation_pct),
                            cpi_division_01 = COALESCE(EXCLUDED.cpi_division_01, gold.dim_nis_official_cpi.cpi_division_01),
                            cpi_division_02 = COALESCE(EXCLUDED.cpi_division_02, gold.dim_nis_official_cpi.cpi_division_02),
                            cpi_division_03 = COALESCE(EXCLUDED.cpi_division_03, gold.dim_nis_official_cpi.cpi_division_03),
                            cpi_division_04 = COALESCE(EXCLUDED.cpi_division_04, gold.dim_nis_official_cpi.cpi_division_04),
                            cpi_division_05 = COALESCE(EXCLUDED.cpi_division_05, gold.dim_nis_official_cpi.cpi_division_05),
                            cpi_division_06 = COALESCE(EXCLUDED.cpi_division_06, gold.dim_nis_official_cpi.cpi_division_06),
                            cpi_division_07 = COALESCE(EXCLUDED.cpi_division_07, gold.dim_nis_official_cpi.cpi_division_07),
                            cpi_division_08 = COALESCE(EXCLUDED.cpi_division_08, gold.dim_nis_official_cpi.cpi_division_08),
                            cpi_division_09 = COALESCE(EXCLUDED.cpi_division_09, gold.dim_nis_official_cpi.cpi_division_09),
                            cpi_division_10 = COALESCE(EXCLUDED.cpi_division_10, gold.dim_nis_official_cpi.cpi_division_10),
                            cpi_division_11 = COALESCE(EXCLUDED.cpi_division_11, gold.dim_nis_official_cpi.cpi_division_11),
                            cpi_division_12 = COALESCE(EXCLUDED.cpi_division_12, gold.dim_nis_official_cpi.cpi_division_12),
                            release_date = COALESCE(EXCLUDED.release_date, gold.dim_nis_official_cpi.release_date),
                            source_notes = EXCLUDED.source_notes;
                        """,
                        (
                            record["cpi_month"],
                            record["headline_cpi"],
                            record["core_cpi"],
                            record["mom_inflation_pct"],
                            record["yoy_inflation_pct"],
                            record.get("cpi_division_01"),
                            record.get("cpi_division_02"),
                            record.get("cpi_division_03"),
                            record.get("cpi_division_04"),
                            record.get("cpi_division_05"),
                            record.get("cpi_division_06"),
                            record.get("cpi_division_07"),
                            record.get("cpi_division_08"),
                            record.get("cpi_division_09"),
                            record.get("cpi_division_10"),
                            record.get("cpi_division_11"),
                            record.get("cpi_division_12"),
                            record["release_date"],
                            record["source_notes"],
                        ),
                    )
                    conn.commit()
                    db_status = "upserted"
                    log.info("Upserted NIS record for %s into gold.dim_nis_official_cpi.", record["cpi_month"])
            except Exception as e:
                log.error("Failed to upsert NIS record into database: %s", e)
                db_status = f"error: {e}"
            finally:
                if should_close:
                    conn.close()

        # 2. Sync to dbt Seed CSV
        seed_status = "skipped"
        if sync_seed:
            try:
                self.sync_to_seed_csv(record)
                seed_status = "synced"
            except Exception as e:
                log.error("Failed to sync NIS record to seed CSV: %s", e)
                seed_status = f"error: {e}"

        return {
            "status": "success" if db_status != "error" else "partial",
            "db_status": db_status,
            "seed_status": seed_status,
            "record": record,
        }

    def sync_to_seed_csv(self, record: dict[str, Any]) -> None:
        """Reads, upserts, and re-writes the dbt seed CSV file chronologically."""
        fieldnames = [
            "cpi_month",
            "headline_cpi",
            "core_cpi",
            "mom_inflation_pct",
            "yoy_inflation_pct",
            "cpi_division_01",
            "cpi_division_02",
            "cpi_division_03",
            "cpi_division_04",
            "cpi_division_05",
            "cpi_division_06",
            "cpi_division_07",
            "cpi_division_08",
            "cpi_division_09",
            "cpi_division_10",
            "cpi_division_11",
            "cpi_division_12",
            "release_date",
            "source_notes",
        ]

        rows_by_month: dict[str, dict[str, Any]] = {}
        if os.path.exists(self.seed_file_path):
            with open(self.seed_file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get("cpi_month"):
                        rows_by_month[r["cpi_month"]] = r

        # Format record for CSV
        csv_row = {
            "cpi_month": record["cpi_month"],
            "headline_cpi": f"{record['headline_cpi']:.4f}",
            "core_cpi": f"{record['core_cpi']:.4f}" if record.get("core_cpi") is not None else "",
            "mom_inflation_pct": (
                f"{record['mom_inflation_pct']:.4f}" if record.get("mom_inflation_pct") is not None else ""
            ),
            "yoy_inflation_pct": (
                f"{record['yoy_inflation_pct']:.4f}" if record.get("yoy_inflation_pct") is not None else ""
            ),
            "release_date": record.get("release_date") or "",
            "source_notes": record.get("source_notes", ""),
        }
        for d in range(1, 13):
            col_name = f"cpi_division_{d:02d}"
            v = record.get(col_name)
            if v is not None and str(v).strip() != "":
                csv_row[col_name] = f"{float(v):.4f}"
            else:
                csv_row[col_name] = rows_by_month.get(record["cpi_month"], {}).get(col_name, "")

        # Upsert
        rows_by_month[record["cpi_month"]] = csv_row

        # Sort ascending by month
        sorted_rows = sorted(rows_by_month.values(), key=lambda x: x["cpi_month"])

        os.makedirs(os.path.dirname(self.seed_file_path), exist_ok=True)
        with open(self.seed_file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in sorted_rows:
                writer.writerow(r)

        log.info("Synchronized seed CSV %s (%d records).", self.seed_file_path, len(sorted_rows))

    def fetch_from_portal(self) -> list[dict[str, Any]]:
        """Scrapes published monthly CPI Excel tables from the official NIS Cambodia portal.

        Navigates to the National Consumer Price Index directory on NIS Cambodia
        (https://nis.gov.kh/សន្ទស្សន៍ថ្នាក់ជាតិ/), downloads any newly published
        monthly Excel files (`CPI-12-group-*.xls` / `*.xlsx`), extracts the official
        headline index, MoM % change, and YoY % change, and synchronizes the seed/database.
        """
        import io
        import requests
        from bs4 import BeautifulSoup
        import pandas as pd
        import urllib3

        urllib3.disable_warnings()

        portal_url = "https://nis.gov.kh/%e1%9e%9f%e1%9e%93%e1%9f%92%e1%9e%91%e1%9e%9f%e1%9f%92%e1%9e%9f%e1%9e%93%e1%9f%8d%e1%9e%90%e1%9f%92%e1%9e%93%e1%9e%b6%e1%9e%80%e1%9f%8b%e1%9e%87%e1%9e%b6%e1%9e%8f%e1%9e%b7/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        discovered_records: list[dict[str, Any]] = []

        try:
            log.info("Scraping NIS National CPI portal at %s...", portal_url)
            resp = requests.get(portal_url, headers=headers, verify=False, timeout=15)
            if resp.status_code != 200:
                log.error("Failed to load NIS portal: HTTP %d", resp.status_code)
                return discovered_records

            soup = BeautifulSoup(resp.text, "html.parser")
            excel_links: list[tuple[str, str]] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if (href.endswith(".xls") or href.endswith(".xlsx")) and "CPI-12-group" in href:
                    text = a.get_text(strip=True)
                    if (text, href) not in excel_links:
                        excel_links.append((text, href))

            log.info("Found %d monthly CPI Excel files on NIS portal.", len(excel_links))

            for text, href in excel_links:
                try:
                    file_resp = requests.get(href, headers=headers, verify=False, timeout=20)
                    if file_resp.status_code != 200:
                        log.warning("Could not download %s (HTTP %d)", href, file_resp.status_code)
                        continue

                    parsed_record = self._parse_cpi_excel(file_resp.content, source_url=href)
                    if parsed_record:
                        res = self.ingest_record(
                            cpi_month=parsed_record["cpi_month"],
                            headline_cpi=parsed_record["headline_cpi"],
                            core_cpi=parsed_record.get("core_cpi"),
                            mom_inflation_pct=parsed_record.get("mom_inflation_pct"),
                            yoy_inflation_pct=parsed_record.get("yoy_inflation_pct"),
                            division_indices=parsed_record.get("division_indices"),
                            release_date=parsed_record.get("release_date"),
                            source_notes=parsed_record.get("source_notes", f"Scraped from NIS Cambodia ({href})"),
                            sync_seed=True,
                        )
                        discovered_records.append(res)
                except Exception as ex:
                    log.error("Error parsing Excel file %s: %s", href, ex)

        except Exception as e:
            log.error("Failed to scrape NIS portal: %s", e)

        return discovered_records

    def _parse_cpi_excel(self, file_content: bytes, source_url: str = "") -> dict[str, Any] | None:
        """Extracts target month, headline CPI, and MoM/YoY inflation from an NIS Excel sheet."""
        import io
        import pandas as pd

        xl = pd.ExcelFile(io.BytesIO(file_content))
        df = xl.parse(xl.sheet_names[0])

        # 1. Detect target month date column (Row index 4 typically contains timestamp objects or strings like 'Jun 2026')
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
            "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
        }
        target_month_str = None
        date_col_idx = 5  # Default to latest month column (index 5)

        for r_idx in range(min(10, len(df))):
            row = df.iloc[r_idx]
            for c_idx, val in enumerate(row):
                if isinstance(val, (datetime, date)):
                    target_month_str = val.strftime("%Y-%m-01")
                    date_col_idx = c_idx
                elif isinstance(val, str):
                    s_clean = val.strip()
                    if re.match(r"^\d{4}-\d{2}-\d{2}", s_clean):
                        target_month_str = s_clean[:7] + "-01"
                        date_col_idx = c_idx
                    else:
                        m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", s_clean, re.IGNORECASE)
                        if m:
                            mon_num = month_map.get(m.group(1).lower()[:3], "01")
                            target_month_str = f"{m.group(2)}-{mon_num}-01"
                            date_col_idx = c_idx

        if not target_month_str:
            log.warning("Could not identify target date column in Excel (%s)", source_url)
            return None

        # 2. Extract All-Items / Headline row (Row with Code '00' or 0) and 12 COICOP Divisions ('01' to '12')
        headline_cpi = None
        mom_pct = None
        yoy_pct = None
        division_indices: dict[str, float] = {}

        for r_idx in range(len(df)):
            raw_code = str(df.iloc[r_idx, 0]).strip()
            if raw_code in ["00", "0", "0.0"]:
                # Col date_col_idx contains the headline index
                raw_cpi = df.iloc[r_idx, date_col_idx]
                if pd.notna(raw_cpi):
                    headline_cpi = round(float(raw_cpi), 4)

                # MoM and YoY percent change are typically in the next two columns
                if len(df.columns) > date_col_idx + 1 and pd.notna(df.iloc[r_idx, date_col_idx + 1]):
                    try:
                        mom_pct = round(float(df.iloc[r_idx, date_col_idx + 1]), 4)
                    except (ValueError, TypeError):
                        pass
                if len(df.columns) > date_col_idx + 2 and pd.notna(df.iloc[r_idx, date_col_idx + 2]):
                    try:
                        yoy_pct = round(float(df.iloc[r_idx, date_col_idx + 2]), 4)
                    except (ValueError, TypeError):
                        pass
            elif raw_code.isdigit() or (len(raw_code) == 2 and raw_code.startswith("0")):
                try:
                    num_val = int(raw_code)
                    if 1 <= num_val <= 12:
                        div_key = f"{num_val:02d}"
                        val = df.iloc[r_idx, date_col_idx]
                        if pd.notna(val):
                            division_indices[div_key] = round(float(val), 4)
                except (ValueError, TypeError):
                    pass

        if headline_cpi is None:
            log.warning("Could not extract headline CPI index from row 00 in %s", source_url)
            return None

        return {
            "cpi_month": target_month_str,
            "headline_cpi": headline_cpi,
            "core_cpi": None,
            "mom_inflation_pct": mom_pct,
            "yoy_inflation_pct": yoy_pct,
            "division_indices": division_indices,
            "release_date": None,
            "source_notes": f"Scraped from NIS Official Excel ({source_url.split('/')[-1]})",
        }


def main() -> None:
    """CLI interface for NIS CPI Benchmark Importer."""
    parser = argparse.ArgumentParser(description="Official NIS Monthly CPI Benchmark Ingestion")
    parser.add_argument("--fetch", action="store_true", help="Fetch latest available release from portal")
    parser.add_argument("--month", type=str, help="CPI month (YYYY-MM-01)")
    parser.add_argument("--headline", type=float, help="Headline CPI index number")
    parser.add_argument("--core", type=float, default=None, help="Core CPI index number")
    parser.add_argument("--mom", type=float, default=None, help="MoM inflation %")
    parser.add_argument("--yoy", type=float, default=None, help="YoY inflation %")
    parser.add_argument("--date", type=str, default=None, help="Release date (YYYY-MM-DD)")
    parser.add_argument("--notes", type=str, default="NIS Cambodia Official CPI Report", help="Provenance note")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    importer = NISBenchmarkImporter()

    if args.month and args.headline is not None:
        res = importer.ingest_record(
            cpi_month=args.month,
            headline_cpi=args.headline,
            core_cpi=args.core,
            mom_inflation_pct=args.mom,
            yoy_inflation_pct=args.yoy,
            release_date=args.date,
            source_notes=args.notes,
        )
        print(f"Ingestion result: {res}")
    elif args.fetch:
        records = importer.fetch_from_portal()
        print(f"Discovered {len(records)} records from NIS portal.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
