import json
import unittest
import uuid

from unittest.mock import MagicMock

from pipeline.bronze_scraper import BronzeScraper


class TestBronzeScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = BronzeScraper()
        self.store_id = "test_store"
        self.source_name = "Test Source"
        self.batch_id = uuid.uuid4()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    def test_parse_records_valid_json(self):
        raw_data = json.dumps(
            [
                {
                    "item_description": "Apple",
                    "price": 1.5,
                    "currency": "USD",
                    "url": "http://apple",
                }
            ]
        )
        records = self.scraper.parse_records(raw_data, self.source_name, self.store_id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["item_description_raw"], "Apple")
        self.assertEqual(records[0]["price"], 1.5)
        self.assertEqual(records[0]["currency"], "USD")

    def test_parse_records_malformed_data(self):
        raw_data = json.dumps([{"item_description": "Banana"}])
        records = self.scraper.parse_records(raw_data, self.source_name, self.store_id)
        self.assertEqual(len(records), 0)

        records = self.scraper.parse_records(
            "invalid json", self.source_name, self.store_id
        )
        self.assertEqual(len(records), 0)


if __name__ == "__main__":
    unittest.main()
