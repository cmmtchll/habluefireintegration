"""Exercise explicit MQTT cleanup and independent receive freshness."""

import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.bluefire.protocol import J1587Report, PgnReport
from custom_components.bluefire.telemetry import Frame, MqttBridge


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.publish = AsyncMock()
        self.confirm = AsyncMock()
        self.save = AsyncMock()
        self.save_j1587 = AsyncMock()
        self.save_identity = AsyncMock()
        self.identity = {
            "mid": 234, "pid": 237, "data": b"EXAMPLE".hex(),
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        self.bridge = MqttBridge(
            "coach", self.publish, discovery_prefix="custom",
            known_signals=[[0, 190], [0, 247], [3, -65226]],
            known_j1587=[
                [128, 190], [191, 92], [191, 250], [130, 194], [234, 237],
            ],
            save_discovery=self.save, save_j1587=self.save_j1587,
            known_identification=[self.identity],
            save_identification=self.save_identity,
        )

    async def test_preview_lists_owned_candidates_without_side_effects(self):
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes(2))
        )
        self.publish.reset_mock()
        result = await self.bridge.async_cleanup_unobserved(self.confirm)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["count"], 7)
        self.confirm.assert_not_awaited()
        self.publish.assert_not_awaited()
        self.save.assert_not_awaited()
        self.save_j1587.assert_not_awaited()
        self.save_identity.assert_not_awaited()
        for entity in result["entities"]:
            self.assertTrue(entity["discovery_topic"].startswith(
                "custom/sensor/bluefire_coach_"
            ))
            self.assertNotIn("connectivity", entity["discovery_topic"])
            self.assertNotIn("last_data", entity["discovery_topic"])
            self.assertNotEqual(
                (entity["controller"], entity.get("pid")), (128, 190)
            )
        self.assertEqual(
            len(self.bridge.j1587.identification_reports), 1
        )

    async def test_cleanup_confirms_deletions_before_saving_ownership(self):
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes(2))
        )
        events = []
        self.confirm.side_effect = lambda topic: events.append(topic)
        self.save.side_effect = lambda ids: events.append(("j1939", ids))
        self.save_j1587.side_effect = lambda ids: events.append(("j1587", ids))
        listener = Mock()
        self.bridge.j1587.add_identification_listener(listener)
        result = await self.bridge.async_cleanup_unobserved(
            self.confirm, dry_run=False,
        )
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["count"], 7)
        for entity in result["entities"]:
            self.assertIn(entity["discovery_topic"], events)
            if entity["retained_state_topic"]:
                self.assertIn(entity["retained_state_topic"], events)
        self.assertEqual(self.confirm.await_count, 10)
        self.assertGreater(events.index(("j1939", [])), events.index(
            "vehicle/coach/j1939/0/spn/247"
        ))
        self.assertEqual(events[-1], ("j1587", [[128, 190]]))
        self.save_identity.assert_awaited_once_with([])
        listener.assert_called_once_with()
        self.assertEqual(self.bridge.j1587.identification_reports, [])
        self.assertEqual(self.bridge.diagnostics()["known_signals"], [])
        self.assertEqual(
            self.bridge.j1587.diagnostics()["known_signals"], [[128, 190]]
        )
        self.publish.reset_mock()
        await self.bridge.async_rediscover()
        configs = [
            topic for topic, _, _ in (
                call.args for call in self.publish.await_args_list
            ) if topic.endswith("/config")
        ]
        self.assertEqual(len(configs), 5)
        self.assertIn(
            "custom/sensor/bluefire_coach_j1587_128_190/config", configs
        )
        await self.bridge.async_process_j1587(
            J1587Report(191, 92, bytes(1))
        )
        self.assertIn(
            [191, 92], self.bridge.j1587.diagnostics()["known_signals"]
        )

    async def test_unconfirmed_cleanup_preserves_ownership_for_retry(self):
        for failure_at in (1, 3):
            with self.subTest(failure_at=failure_at):
                self.setUp()
                attempts = 0

                async def confirm(topic):
                    nonlocal attempts
                    attempts += 1
                    if attempts == failure_at:
                        raise TimeoutError

                self.confirm.side_effect = confirm
                before = self.bridge.diagnostics()
                with self.assertRaises(TimeoutError):
                    await self.bridge.async_cleanup_unobserved(
                        self.confirm, dry_run=False,
                    )
                self.assertEqual(self.bridge.diagnostics(), before)
                self.save.assert_not_awaited()
                self.save_j1587.assert_not_awaited()
                self.save_identity.assert_not_awaited()
                self.confirm.side_effect = None
                result = await self.bridge.async_cleanup_unobserved(
                    self.confirm, dry_run=False,
                )
                self.assertEqual(result["count"], 8)

    async def test_received_since_preview_is_preserved_across_reconnects(self):
        await self.bridge.async_cleanup_unobserved(self.confirm)
        await self.bridge.async_process_j1587(
            J1587Report(234, 237, b"EXAMPLE")
        )
        await self.bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes(8))
        )
        await self.bridge.async_disconnected()
        await self.bridge.async_rediscover()
        self.save_identity.reset_mock()
        result = await self.bridge.async_cleanup_unobserved(
            self.confirm, dry_run=False,
        )
        self.assertEqual(result["count"], 6)
        self.assertEqual(self.bridge.j1587.identification_reports[0]["value"],
                         "EXAMPLE")
        saved_identity = self.save_identity.call_args.args[0]
        self.assertEqual(saved_identity[0]["mid"], 234)
        self.assertEqual(saved_identity[0]["pid"], 237)
        self.assertEqual(
            self.bridge.diagnostics()["known_signals"], [[0, 190], [0, 513]]
        )

    async def test_pgn_observations_protect_only_matching_protocol_entities(
        self,
    ):
        await self.bridge.async_process_pgn_report(
            PgnReport(0, 61444, 6, 0, bytes(8))
        )
        result = await self.bridge.async_cleanup_unobserved(self.confirm)
        self.assertEqual(result["count"], 7)
        self.assertFalse(any(
            entity.get("spn") == 190 for entity in result["entities"]
        ))
        self.assertTrue(any(
            entity.get("pid") == 190 for entity in result["entities"]
        ))

    async def test_empty_cleanup_is_idempotent(self):
        await self.bridge.async_cleanup_unobserved(self.confirm, dry_run=False)
        self.confirm.reset_mock()
        result = await self.bridge.async_cleanup_unobserved(
            self.confirm, dry_run=False,
        )
        self.assertEqual(result, {
            "dry_run": False, "count": 0, "entities": [],
        })
        self.confirm.assert_not_awaited()


class ReceiveFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_freshness_survives_mqtt_failure_and_expires(self):
        clock = [0]
        publish = AsyncMock(side_effect=RuntimeError("MQTT down"))
        bridge = MqttBridge("coach", publish, clock=lambda: clock[0])
        self.assertFalse(bridge.j1587.telemetry_connected)
        with self.assertRaisesRegex(RuntimeError, "MQTT down"):
            await bridge.async_process_j1587(
                J1587Report(128, 190, bytes(2))
            )
        self.assertTrue(bridge.j1587.telemetry_connected)
        self.assertFalse(bridge.telemetry_connected)
        clock[0] = 60
        self.assertFalse(bridge.j1587.telemetry_connected)

    async def test_native_freshness_polling_timeout_and_broker_reconnect(self):
        clock = [0]
        bridge = MqttBridge(
            "coach", AsyncMock(), clock=lambda: clock[0], j1708_polling=True,
        )
        await bridge.async_process_j1587(J1587Report(128, 190, bytes(2)))
        await bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes(8))
        )
        await bridge.async_disconnected(reset_receive=False)
        self.assertTrue(bridge.telemetry_connected)
        self.assertTrue(bridge.j1587.telemetry_connected)
        clock[0] = 60
        self.assertFalse(bridge.telemetry_connected)
        self.assertTrue(bridge.j1587.telemetry_connected)
        clock[0] = 180
        self.assertFalse(bridge.j1587.telemetry_connected)
        await bridge.async_process_j1587(J1587Report(128, 190, bytes(2)))
        await bridge.async_disconnected()
        self.assertFalse(bridge.j1587.telemetry_connected)

    async def test_replayed_identity_does_not_establish_receive_freshness(
        self,
    ):
        bridge = MqttBridge("coach", AsyncMock(), known_identification=[{
            "mid": 128, "pid": 243, "data": b"EXAMPLE".hex(),
            "timestamp": "2026-01-01T00:00:00+00:00",
        }])
        await bridge.async_rediscover()
        self.assertFalse(bridge.j1587.telemetry_connected)
        self.assertTrue(bridge.j1587.identification_reports)

    async def test_invalid_reports_do_not_establish_receive_freshness(self):
        bridge = MqttBridge("coach", AsyncMock())
        with self.assertRaises(ValueError):
            await bridge.async_process_j1587(
                J1587Report(127, 190, bytes(2))
            )
        self.assertFalse(bridge.j1587.telemetry_connected)
        self.assertEqual(bridge.j1587._observed_signals, set())
