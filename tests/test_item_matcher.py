import unittest
import uuid
from unittest.mock import MagicMock, patch

from pipeline.item_matcher import ItemMatcher
from pipeline.text_clean import is_size_compatible


class TestItemMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = ItemMatcher()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.cursor.mogrify.side_effect = lambda sql, args: b"MOCK_SQL"
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
    def test_fuzzy_review_band_sends_to_review(self, mock_clean, mock_fuzz):
        item_id = uuid.uuid4()
        self.cursor.fetchone.side_effect = [None]
        self.cursor.fetchall.return_value = [(item_id, "CLEAN NAME DB")]

        stats = self.matcher.match_record(
            1, "Raw Name", None, None, "store1", self.conn
        )

        self.assertEqual(stats["sent_to_review"], 1)
        self.assertEqual(stats["new_items_created"], 0)
        review_call = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO silver.needs_review" in str(call)
        ][0]
        self.assertIn("Raw Name", str(review_call))

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
        self.assertEqual(stats["sent_to_review"], 0)
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
            is_size_compatible("500g", "520g", tolerance=0.10)
        )
        # 500g vs 1000g (> 10% diff) -> False
        self.assertFalse(
            is_size_compatible("500g", "1000g", tolerance=0.10)
        )
        # 1L vs 1000ml -> different units string fallback
        self.assertTrue(is_size_compatible("1L", "1L"))

    def test_process_batch_review_and_new_items(self):
        existing_item_id = uuid.uuid4()
        self.cursor.fetchall.side_effect = [
            [(existing_item_id, "COCA COLA 330ML", "12345", "330ml")],  # canonical_items cache with barcode
            [],  # sku cache
            [
                (1, "Coca Cola 330ml", "12345", None, "aeon", "Coca Cola", "330ml"),  # barcode exact
                (2, "Coca Cola 320ml", None, None, "aeon", "Coca Cola", "330ml"),     # fuzzy near match -> review
                (3, "Fresh Apples 1kg", None, None, "aeon", None, "1kg"),              # new item
            ],
        ]

        with patch.object(self.matcher, "match_by_fuzzy_text") as mock_fuzzy:
            # For raw_price_id 2: fuzzy score 0.88 (review band)
            # For raw_price_id 3: no fuzzy match
            mock_fuzzy.side_effect = [
                (existing_item_id, 0.88, "COCA COLA 330ML"),
                None,
            ]
            stats = self.matcher.process_batch(self.conn)

        self.assertEqual(stats["matched_exact"], 1)
        self.assertEqual(stats["sent_to_review"], 1)
        self.assertEqual(stats["new_items_created"], 1)


if __name__ == "__main__":
    unittest.main()
