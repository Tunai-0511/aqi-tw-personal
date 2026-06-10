import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tsdb


def _load_record_feel():
    path = ROOT / "scripts" / "record_feel.py"
    spec = importlib.util.spec_from_file_location("record_feel", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RecordFeelTests(unittest.TestCase):
    def test_parse_feel_command_accepts_prefix_and_bare_score(self):
        record_feel = _load_record_feel()

        self.assertEqual(record_feel.parse_score("feel 4"), 4)
        self.assertEqual(record_feel.parse_score("Feel: 2"), 2)
        self.assertEqual(record_feel.parse_score("5"), 5)

    def test_parse_feel_command_rejects_invalid_scores(self):
        record_feel = _load_record_feel()

        for text in ["feel 0", "feel 6", "feel bad", "hello"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    record_feel.parse_score(text)

    def test_record_feel_writes_existing_health_diary_schema(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            tsdb.DB_PATH = Path(td) / "agent_aqi.sqlite"
            record_feel = _load_record_feel()

            result = record_feel.record_feel(
                score=4,
                city_id="taichung",
                outdoor_min=0,
                note="Discord feel command",
                entry_date=date(2026, 6, 8),
            )

            self.assertEqual(result["date"], "2026-06-08")
            self.assertEqual(result["city_id"], "taichung")
            self.assertEqual(result["symptom_score"], 4)

            with sqlite3.connect(tsdb.DB_PATH) as conn:
                row = conn.execute(
                    "SELECT date, city_id, symptom_score, outdoor_min, note FROM health_diary"
                ).fetchone()

            self.assertEqual(row, ("2026-06-08", "taichung", 4, 0, "Discord feel command"))


if __name__ == "__main__":
    unittest.main()
