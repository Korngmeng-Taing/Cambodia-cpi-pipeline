import json
import unittest
import uuid
from unittest.mock import MagicMock, patch

from pipeline.bronze_scraper import BronzeScraper


class TestBronzeScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = BronzeScraper()
        self.scraper.minio = MagicMock()
        self.scraper.archiver = MagicMock()
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

    def test_write_batch_appends(self):
        records = [
            {
                "item_description_raw": "Apple",
                "price": 1.5,
                "currency": "USD",
                "source_url": "",
                "raw_payload": "{}",
            }
        ]
        count = self.scraper.write_batch(
            records, self.conn, self.batch_id, self.store_id, self.source_name
        )
        self.assertEqual(count, 1)
        self.assertTrue(self.cursor.execute.called)

        insert_calls = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO bronze.raw_prices" in str(call)
        ]
        self.assertTrue(insert_calls)

        staging_calls = [
            call
            for call in self.cursor.execute.mock_calls
            if "INSERT INTO staging.raw_scrapes" in str(call)
        ]
        self.assertTrue(staging_calls)

    @patch("pipeline.bronze_scraper.requests.get")
    def test_scrape_and_ingest_retry_logic(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = json.dumps([{"item_description": "Apple", "price": 1.5}])
        mock_get.side_effect = [
            Exception("Transient error"),
            Exception("Transient error"),
            mock_response,
        ]

        self.scraper.scrape_and_ingest(
            self.store_id, self.source_name, "http://test", self.conn
        )

        self.assertEqual(mock_get.call_count, 3)
        self.assertTrue(self.conn.commit.called)

        mock_get.reset_mock()
        mock_get.side_effect = Exception("Permanent error")
        self.scraper.scrape_and_ingest(
            self.store_id, self.source_name, "http://test", self.conn
        )
        self.assertEqual(mock_get.call_count, 3)

        self.assertTrue(
            any(
                "INSERT INTO bronze.scrape_errors" in str(call)
                for call in self.cursor.execute.mock_calls
            )
        )


if __name__ == "__main__":
    unittest.main()
