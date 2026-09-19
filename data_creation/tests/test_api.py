"""Regression test for the measurement ingestion path."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from data_creation.backend import database
from data_creation.middleware.main import app


class ApiTest(unittest.TestCase):
    def test_store_query_summary_and_export(self):
        original_path = database.DATABASE_PATH
        with tempfile.TemporaryDirectory() as directory:
            database.DATABASE_PATH = Path(directory) / "test.db"
            sample = {
                "experiment_id": "wifi-indoor-001",
                "protocol": "WIFI",
                "payload_bytes": 128,
                "packets_sent": 100,
                "packets_received": 98,
                "packets_lost": 2,
                "packet_loss_pct": 2,
                "latency_mean_ms": 18.7,
                "throughput_kbps": 540,
                "successful": True,
            }
            try:
                with TestClient(app) as client:
                    response = client.post("/measurements", json=sample)
                    self.assertEqual(response.status_code, 201)
                    self.assertEqual(response.json()["stored"], 1)
                    self.assertEqual(client.get("/measurements?protocol=WIFI").status_code, 200)
                    self.assertEqual(client.get("/summary").status_code, 200)
                    self.assertTrue(client.get("/export.csv").text.startswith("id,timestamp,experiment_id"))
            finally:
                database.DATABASE_PATH = original_path
