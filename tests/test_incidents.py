"""Incident persistence, retention and explicit telemetry privacy."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.incidents import (
    AFTER_LIMIT, BEFORE_LIMIT, INCIDENT_LIMIT, IncidentJournal,
)


class JournalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.disk = None

        async def save(data):
            self.disk = deepcopy(data)

        self.store = SimpleNamespace(
            async_load=AsyncMock(side_effect=lambda: deepcopy(self.disk)),
            async_save=AsyncMock(side_effect=save),
            async_delay_save=Mock(), async_remove=AsyncMock(),
        )
        self.journal = IncidentJournal(self.store)

    async def test_freezes_pre_window_coalesces_and_bounds_post_window(self):
        for sequence in range(BEFORE_LIMIT + 4):
            self.journal.observe({"sequence": sequence})
        context = {"phase": "receiving"}
        self.journal.record("framing_error", context)
        context["phase"] = "changed externally"
        self.journal.record("gatt_failure", {"phase": "startup"})
        self.assertEqual(
            self.journal.diagnostics()["incidents"][0]["context"]["phase"],
            "receiving",
        )
        for sequence in range(AFTER_LIMIT + 4):
            self.journal.observe({"sequence": sequence + 100})
        record, = self.journal.diagnostics()["incidents"]
        self.assertEqual(record["before"][0]["sequence"], 4)
        self.assertEqual(len(record["before"]), BEFORE_LIMIT)
        self.assertEqual(len(record["after"]), AFTER_LIMIT)
        self.assertEqual(record["triggers"], ["framing_error", "gatt_failure"])
        self.assertEqual(record["latest_context"]["phase"], "startup")
        self.store.async_save.assert_not_awaited()
        await self.journal.async_flush()
        restored = IncidentJournal(self.store)
        await restored.async_load()
        self.assertEqual(
            restored.diagnostics()["incidents"],
            self.journal.diagnostics()["incidents"],
        )
        record["context"]["phase"] = "changed snapshot"
        self.assertEqual(
            self.journal.diagnostics()["incidents"][0]["context"]["phase"],
            "receiving",
        )

    async def test_default_metadata_only_and_disabling_raw_purges_disk(self):
        note = {"sequence": 1, "raw_reports": [{"body_hex": "9a80600164"}]}
        self.journal.observe(note)
        self.journal.record("framing_error", {})
        self.assertNotIn(
            "raw_reports", self.journal.diagnostics()["incidents"][0][
                "before"
            ][0],
        )
        enabled = IncidentJournal(self.store, raw_enabled=True)
        enabled.observe(note)
        enabled.record("framing_error", {})
        await enabled.async_flush()
        self.assertIn("raw_reports", self.disk["incidents"][0]["before"][0])
        disabled = IncidentJournal(self.store)
        await disabled.async_load()
        self.assertNotIn("raw_reports", self.disk["incidents"][0]["before"][0])

    async def test_retention_and_sessions_do_not_join_notifications(self):
        for attempt in range(INCIDENT_LIMIT + 4):
            self.journal.new_session()
            self.journal.observe({"sequence": attempt})
            self.journal.record("connection_failure", {"attempt": attempt})
        records = self.journal.diagnostics()["incidents"]
        self.assertEqual(len(records), INCIDENT_LIMIT)
        self.assertEqual(records[0]["context"]["attempt"], 4)
        self.assertEqual(len(records[-1]["before"]), 1)
        self.journal.new_session()
        self.journal.observe({"sequence": 99})
        self.assertEqual(records[-1]["after"], [])

    async def test_byte_limit_is_enforced_and_oversized_event_is_logged(self):
        with patch("custom_components.bluefire.incidents.INCIDENT_BYTES", 500):
            with self.assertLogs(
                "custom_components.bluefire.incidents", level="WARNING",
            ):
                self.journal.record("test", {"detail": "x" * 1000})
                self.journal.diagnostics()
            self.assertLessEqual(
                len(json.dumps(self.journal._data()).encode()), 500,
            )
        self.assertEqual(self.journal.diagnostics()["dropped_oversized"], 1)
        await self.journal.async_flush()
        restored = IncidentJournal(self.store)
        await restored.async_load()
        self.assertEqual(restored.diagnostics()["dropped_oversized"], 1)

    async def test_removal_prevents_late_callbacks_from_recreating_storage(
        self,
    ):
        self.journal.record("failure", {})
        await self.journal.async_remove()
        self.journal.observe({"sequence": 1})
        self.journal.record("late", {})
        await self.journal.async_flush()
        self.store.async_remove.assert_awaited_once()
        self.store.async_save.assert_not_awaited()
        self.assertEqual(self.journal.diagnostics()["incidents"], [])

    async def test_storage_failures_are_not_success_shaped(self):
        for corrupted in (
            {"incidents": "corrupted"},
            {"incidents": [{}]},
            {"incidents": [], "dropped_oversized": -1},
            {"incidents": [{
                "context": {}, "triggers": [],
                "before": ["invalid notification"], "after": [],
            }]},
        ):
            self.disk = corrupted
            with self.assertRaisesRegex(ValueError, "Invalid"):
                await self.journal.async_load()
        self.journal.record("failure", {})
        self.store.async_save.side_effect = OSError("disk full")
        with self.assertRaisesRegex(OSError, "disk full"):
            await self.journal.async_flush()
        self.store.async_save.side_effect = None
        await self.journal.async_flush()
        self.assertEqual(self.store.async_save.await_count, 2)

    async def test_frequent_observations_do_not_postpone_the_scheduled_save(
        self,
    ):
        self.journal.record("failure", {})
        for sequence in range(AFTER_LIMIT):
            self.journal.observe({"sequence": sequence})
        self.store.async_delay_save.assert_called_once()
        callback = self.store.async_delay_save.call_args.args[0]
        await self.store.async_save(callback())
        self.assertEqual(
            len(self.disk["incidents"][0]["after"]), AFTER_LIMIT,
        )
        self.journal.record("another_failure", {})
        self.assertEqual(self.store.async_delay_save.call_count, 2)

    async def test_session_completion_preserves_initial_and_final_context(
        self,
    ):
        self.journal.record("failure", {"attempt": 1, "phase": "startup"})
        self.journal.finish_session({"attempt": 2})
        self.assertNotIn(
            "final_context", self.journal.diagnostics()["incidents"][0],
        )
        final = {"attempt": 1, "phase": "idle", "cleanup_operations": ["done"]}
        self.journal.finish_session(final)
        self.journal.observe({"sequence": 99})
        record, = self.journal.diagnostics()["incidents"]
        self.assertEqual(record["context"]["phase"], "startup")
        self.assertEqual(record["final_context"], final)
        self.assertEqual(record["after"], [])
        self.assertIn("completed_at", record)

    async def test_notifications_arriving_during_flush_are_saved(self):
        saving = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def save(data):
            nonlocal calls
            calls += 1
            if calls == 1:
                saving.set()
                await release.wait()
            self.disk = deepcopy(data)

        self.store.async_save.side_effect = save
        self.journal.record("failure", {})
        flush = asyncio.create_task(self.journal.async_flush())
        await saving.wait()
        self.journal.observe({"sequence": 2})
        release.set()
        await flush
        self.assertEqual(self.disk["incidents"][0]["after"], [{"sequence": 2}])
        self.assertEqual(calls, 2)

    async def test_remove_waits_for_in_flight_save_then_prevents_recreation(
        self,
    ):
        saving = asyncio.Event()
        release = asyncio.Event()

        async def save(data):
            saving.set()
            await release.wait()

        self.store.async_save.side_effect = save
        self.journal.record("failure", {})
        flush = asyncio.create_task(self.journal.async_flush())
        await saving.wait()
        remove = asyncio.create_task(self.journal.async_remove())
        await asyncio.sleep(0)
        self.journal.record("late", {})
        self.store.async_remove.assert_not_awaited()
        release.set()
        await asyncio.gather(flush, remove)
        self.store.async_remove.assert_awaited_once()
        self.assertEqual(self.store.async_save.await_count, 1)
