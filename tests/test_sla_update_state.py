"""SLA Update Data persisted state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from seller.intelligence.business.sla_update_state import (
    build_snapshot_from_completion,
    load_sla_update_state,
    persist_sla_update_completion,
    save_sla_update_state,
    snapshot_to_refresh_status,
)


class SlaUpdateStateTests(unittest.TestCase):
    def test_persist_and_reload_snapshot(self):
        result = {
            "success": True,
            "refreshed_at": "2026-06-03T12:00:00Z",
            "mapping": {
                "summary": {
                    "mapped": 86,
                    "need_review": 2,
                    "not_found": 6,
                    "total": 94,
                },
                "newly_mapped_count": 61,
                "failed_count": 0,
            },
            "completion_message": "done",
        }
        status = {
            "percent": 100,
            "shops_processed": 94,
            "shops_total": 94,
            "finished_at": "2026-06-03T12:00:01Z",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seller_level_update_state.json"
            saved = persist_sla_update_completion(result, status, path=path)
            self.assertIsNotNone(saved)
            loaded = load_sla_update_state(path)
            self.assertTrue(loaded.get("completed"))
            self.assertEqual(loaded.get("fastmoss_mapped_count"), 86)
            self.assertEqual(loaded.get("pending_review_count"), 2)
            self.assertEqual(loaded.get("still_not_found_count"), 6)
            self.assertEqual(loaded.get("newly_mapped_count"), 61)
            refresh = snapshot_to_refresh_status(loaded)
            self.assertFalse(refresh.get("running"))
            self.assertEqual(refresh.get("percent"), 100)
            self.assertTrue(refresh.get("persisted"))
            self.assertEqual(refresh.get("result"), result)

    def test_failed_run_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seller_level_update_state.json"
            self.assertIsNone(
                persist_sla_update_completion({"success": False}, {"percent": 50}, path=path)
            )
            self.assertIsNone(load_sla_update_state(path))

    def test_build_snapshot_shape(self):
        snap = build_snapshot_from_completion(
            result={
                "success": True,
                "refreshed_at": "2026-06-03T10:00:00Z",
                "mapping": {"summary": {"mapped": 1, "total": 2}},
            },
            status={"percent": 100},
        )
        self.assertTrue(snap.get("completed"))
        self.assertEqual(snap.get("fastmoss_mapped_count"), 1)


if __name__ == "__main__":
    unittest.main()
