import unittest
import uuid
from unittest.mock import MagicMock, patch

from pipeline.item_matcher import ItemMatcher


class TestItemMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = ItemMatcher()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    @patch("pipeline.item_matcher.clean_name_for_matching", return_value="CLEAN NAME")
    def test_barcode_exact(self, mock_clean):
        item_id = uuid.uuid4()
        self.cursor.fetchone.return_value = (item_id,)

        stats = self.matcher.match_record(
            1, "Raw Name", "12345", None, "store1", self.conn
        )

        self.assertEqual(stats["matched_exact"], 1)
        self.cursor.execute.assert_any_call(
            "SELECT item_id FROM silver.canonical_items WHERE barcode = %s", ("12345",)
        )

        log_call = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO silver.item_match_log" in str(call)
        ][0]
        self.assertIn("barcode_exact", str(log_call))

    @patch("pipeline.item_matcher.fuzz.token_sort_ratio", return_value=95.0)
    @patch("pipeline.item_matcher.clean_name_for_matching", return_value="CLEAN NAME")
    def test_fuzzy_auto_accept(self, mock_clean, mock_fuzz):
        item_id = uuid.uuid4()
        self.cursor.fetchone.side_effect = [None]
        self.cursor.fetchall.return_value = [(item_id, "CLEAN NAME DB")]

        stats = self.matcher.match_record(
            1, "Raw Name", None, None, "store1", self.conn
        )

        self.assertEqual(stats["matched_fuzzy"], 1)
        log_call = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO silver.item_match_log" in str(call)
        ][0]
        self.assertIn("fuzzy_text", str(log_call))

    @patch("pipeline.item_matcher.fuzz.token_sort_ratio", return_value=90.0)
    @patch("pipeline.item_matcher.clean_name_for_matching", return_value="CLEAN NAME")
    def test_fuzzy_needs_review(self, mock_clean, mock_fuzz):
        item_id = uuid.uuid4()
        self.cursor.fetchone.side_effect = [None]
        self.cursor.fetchall.return_value = [(item_id, "CLEAN NAME DB")]

        stats = self.matcher.match_record(
            1, "Raw Name", None, None, "store1", self.conn
        )

        self.assertEqual(stats["sent_to_review"], 1)
        review_call = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO silver.needs_review" in str(call)
        ][0]
        self.assertIn("INSERT INTO silver.needs_review", str(review_call))

    @patch("pipeline.item_matcher.fuzz.token_sort_ratio", return_value=50.0)
    @patch("pipeline.item_matcher.clean_name_for_matching", return_value="CLEAN NAME")
    def test_new_item_created(self, mock_clean, mock_fuzz):
        new_item_id = uuid.uuid4()
        # barcode=None → match_by_barcode returns early without calling fetchone
        # create_canonical_item is the first (and only) fetchone call
        self.cursor.fetchone.return_value = (new_item_id,)
        self.cursor.fetchall.return_value = [(uuid.uuid4(), "COMPLETELY DIFFERENT")]

        stats = self.matcher.match_record(
            1, "Raw Name", None, None, "store1", self.conn
        )

        self.assertEqual(stats["new_items_created"], 1)
        log_call = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO silver.item_match_log" in str(call)
        ][0]
        self.assertIn("new_item", str(log_call))

    def test_match_by_sku(self):
        item_id = uuid.uuid4()
        self.matcher.sku_cache[("aeon", "SKU123")] = item_id

        match = self.matcher.match_by_sku("aeon", "SKU123")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], item_id)
        self.assertEqual(match[1], 1.0)

    def test_size_compatibility_tolerance(self):
        # 500g vs 520g (<= 10% diff) -> True
        self.assertTrue(
            self.matcher._is_size_compatible("500g", "520g", tolerance=0.10)
        )
        # 500g vs 1000g (> 10% diff) -> False
        self.assertFalse(
            self.matcher._is_size_compatible("500g", "1000g", tolerance=0.10)
        )
        # 1L vs 1000ml -> different units string fallback
        self.assertTrue(self.matcher._is_size_compatible("1L", "1L"))

    def test_process_batch_with_scrape_date(self):
        self.cursor.fetchall.side_effect = [
            [],  # canonical_items cache
            [],  # dim_canonical_products sku cache
            [],  # raw_prices query rows
        ]
        stats = self.matcher.process_batch(
            self.conn, limit=500, scrape_date="2026-08-23"
        )
        self.assertEqual(stats["matched_exact"], 0)
        # Check that query executed includes scrape_date condition
        calls = [str(call) for call in self.cursor.execute.mock_calls]
        query_call = [c for c in calls if "rp.scraped_at::date = %s::date" in c]
        self.assertTrue(len(query_call) > 0)


if __name__ == "__main__":
    unittest.main()
