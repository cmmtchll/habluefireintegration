"""Test durable discovery ownership and deferred broker cleanup."""

from copy import deepcopy
import asyncio
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.mqtt import (
    DiscoveryLedger,
    async_confirm_removal,
    mqtt_settings,
)
from test_boundaries import module


def record(prefix="homeassistant", signals=None, pending=False):
    return {
        "vehicle_id": "coach",
        "discovery_prefix": prefix,
        "signals": [[0, 190]] if signals is None else signals,
        "pending": pending,
        "pending_offline": False,
    }


class SettingsTests(unittest.TestCase):
    def settings(self, data, options):
        entry = SimpleNamespace(data=data, options=options)
        hass = SimpleNamespace(config_entries=SimpleNamespace(
            async_entries=Mock(return_value=[entry])
        ))
        return mqtt_settings(hass)

    def test_options_override_data_without_exposing_credentials(self):
        settings = self.settings(
            {"discovery_prefix": "old", "password": "not-a-real-password"},
            {"discovery_prefix": "ha/custom", "birth_message": {
                "topic": "ha/ready", "payload": "ready",
            }},
        )
        self.assertEqual(settings.discovery_prefix, "ha/custom")
        self.assertEqual(settings.birth_topic, "ha/ready")
        self.assertEqual(settings.birth_payload, "ready")
        self.assertNotIn("password", vars(settings))

    def test_default_birth_is_independent_of_custom_discovery_prefix(self):
        settings = self.settings({}, {"discovery_prefix": "custom"})
        self.assertEqual(settings.birth_topic, "homeassistant/status")
        self.assertEqual(settings.birth_payload, "online")

    def test_birth_can_be_disabled(self):
        self.assertIsNone(self.settings({}, {
            "birth_message": {},
        }).birth_topic)


class LedgerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.disk = {}
        self.store = SimpleNamespace(
            async_load=AsyncMock(side_effect=lambda: deepcopy(self.disk)),
            async_save=AsyncMock(side_effect=self.save),
        )
        self.ledger = DiscoveryLedger(self.store)
        self.publish = AsyncMock()

    async def save(self, records):
        self.disk = deepcopy(records)

    async def test_ownership_persists_across_new_ledger_instance(self):
        await self.ledger.async_prepare("entry", "coach", "homeassistant")
        await self.ledger.async_save_signals("entry", [[0, 190]])
        restored = DiscoveryLedger(self.store)
        signals = await restored.async_prepare(
            "entry", "coach", "homeassistant"
        )
        self.assertEqual(signals, [[0, 190]])
        self.assertEqual(set(self.disk["entry"]), {
            "vehicle_id", "discovery_prefix", "signals", "pending",
            "j1587_signals", "pending_offline",
            "identification",
        })

    async def test_j1587_survives_reload_prefix_change_and_entry_removal(self):
        await self.ledger.async_prepare("entry", "coach", "homeassistant")
        await self.ledger.async_save_signals(
            "entry", [[128, 190], [130, 194]], j1587=True
        )
        await self.ledger.async_save_signals("entry", [[0, 190]])
        restored = DiscoveryLedger(self.store)
        self.assertEqual(
            await restored.async_prepare("entry", "coach", "custom"),
            [[0, 190]],
        )
        self.assertEqual(await restored.async_get_j1587("entry"),
                         [[128, 190], [130, 194]])
        await restored.async_flush_removals(self.publish)
        for mid, pid in ((128, 190), (130, 194)):
            self.publish.assert_any_await(
                "homeassistant/sensor/"
                f"bluefire_coach_j1587_{mid}_{pid}/config", "", True,
            )
        self.assertFalse(any(
            args.args == ("vehicle/coach/j1587/availability", "", True)
            for args in self.publish.await_args_list
        ))
        self.publish.reset_mock()
        await restored.async_queue_removal("entry")
        await DiscoveryLedger(self.store).async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})
        self.publish.assert_any_await(
            "custom/sensor/bluefire_coach_j1587_130_194/config", "", True
        )
        self.publish.assert_any_await(
            "vehicle/coach/j1587/availability", "", True
        )

    async def test_identity_survives_restart_and_prefix_but_not_vehicle_change(
        self,
    ):
        identity = [{
            "mid": 128, "pid": 237, "data": b"EXAMPLE VIN".hex(),
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        await self.ledger.async_prepare("entry", "coach", "homeassistant")
        await self.ledger.async_save_signals(
            "entry", [[128, 237], [128, 245]], j1587=True
        )
        await self.ledger.async_save_identification("entry", identity)
        restored = DiscoveryLedger(self.store)
        await restored.async_prepare("entry", "coach", "custom")
        self.assertEqual(await restored.async_get_identification("entry"),
                         identity)
        await restored.async_flush_removals(self.publish)
        self.assertFalse(any(
            "/pid/" in call.args[0]
            for call in self.publish.await_args_list
        ))
        await restored.async_prepare("entry", "new_coach", "custom")
        self.assertEqual(await restored.async_get_identification("entry"), [])
        self.publish.reset_mock()
        await restored.async_flush_removals(self.publish)
        for pid in (237, 245):
            self.publish.assert_any_await(
                f"vehicle/coach/j1587/128/pid/{pid}", "", True
            )
        self.assertEqual(list(self.disk), ["entry"])

    async def test_retained_state_removal_retries_after_broker_failure(self):
        await self.ledger.async_prepare("entry", "coach", "homeassistant")
        await self.ledger.async_save_signals(
            "entry", [[128, 237], [128, 245]], j1587=True
        )
        await self.ledger.async_save_identification("entry", [{
            "mid": 128, "pid": 237, "data": b"EXAMPLE VIN".hex(),
            "timestamp": "2026-01-01T00:00:00+00:00",
        }])
        await self.ledger.async_queue_removal("entry")
        self.assertEqual(self.disk["entry"]["identification"], [])

        async def publish(topic, payload, retain):
            if topic.endswith("/pid/245"):
                raise RuntimeError("broker disconnected")

        with self.assertRaisesRegex(RuntimeError, "broker disconnected"):
            await self.ledger.async_flush_removals(publish)
        self.assertTrue(self.disk["entry"]["pending"])
        await DiscoveryLedger(self.store).async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})
        for pid in (237, 245):
            self.publish.assert_any_await(
                f"vehicle/coach/j1587/128/pid/{pid}", "", True
            )

    async def test_old_ledger_preserves_protocol_identity_boundaries(self):
        self.disk = {"entry": {
            **record(), "j1587_signals": [
                [128, 190], [128, 513], [0, 190], [130, 194], [130, True],
            ],
        }}
        restored = DiscoveryLedger(self.store)
        self.assertEqual(await restored.async_prepare(
            "entry", "coach", "homeassistant"), [[0, 190]])
        self.assertEqual(await restored.async_get_j1587("entry"),
                         [[128, 190], [130, 194]])

    async def test_prefix_change_withdraws_old_definitions(self):
        self.disk = {"entry": record()}
        signals = await self.ledger.async_prepare("entry", "coach", "custom")
        self.assertEqual(signals, [[0, 190]])
        await self.ledger.async_flush_removals(self.publish)
        self.assertEqual(list(self.disk), ["entry"])
        self.assertFalse(self.disk["entry"]["pending"])
        topics = [call.args[0] for call in self.publish.await_args_list]
        self.assertIn(
            "homeassistant/sensor/bluefire_coach_0_190/config", topics
        )
        self.assertNotIn("custom/sensor/bluefire_coach_0_190/config", topics)
        self.assertFalse(any(
            call.args == ("vehicle/coach/j1939/availability", "", True)
            for call in self.publish.await_args_list
        ))
        for protocol in ("j1939", "j1587"):
            self.publish.assert_any_await(
                "homeassistant/binary_sensor/"
                f"bluefire_coach_{protocol}_connectivity/config", "", True,
            )
            self.assertNotIn(
                "custom/binary_sensor/"
                f"bluefire_coach_{protocol}_connectivity/config", topics,
            )

    async def test_removal_survives_restart_without_runtime_bridge(self):
        self.disk = {"entry": record()}
        await self.ledger.async_queue_removal("entry")
        self.assertTrue(self.disk["entry"]["pending"])
        restored = DiscoveryLedger(self.store)
        await restored.async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})
        self.publish.assert_any_await(
            "homeassistant/sensor/bluefire_coach_0_190/config", "", True
        )
        self.publish.assert_any_await(
            "vehicle/coach/j1939/availability", "", True
        )
        for protocol in ("j1939", "j1587"):
            self.publish.assert_any_await(
                "homeassistant/binary_sensor/"
                f"bluefire_coach_{protocol}_connectivity/config", "", True,
            )

    async def test_fault_ownership_survives_restart_and_prefix_change(self):
        self.disk = {
            "entry": record(signals=[[0, 190], [3, -65226], [11, -65227]])
        }
        await self.ledger.async_prepare("entry", "coach", "custom")
        restored = DiscoveryLedger(self.store)
        await restored.async_flush_removals(self.publish)
        for source, identity in ((0, 190), (3, -65226), (11, -65227)):
            self.publish.assert_any_await(
                "homeassistant/sensor/"
                f"bluefire_coach_{source}_{identity}/config", "", True,
            )
        self.assertEqual(
            self.disk["entry"]["signals"],
            [[0, 190], [3, -65226], [11, -65227]],
        )
        await restored.async_queue_removal("entry")
        await DiscoveryLedger(self.store).async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})
        self.publish.assert_any_await(
            "custom/sensor/bluefire_coach_3_-65226/config", "", True
        )

    async def test_failed_cleanup_retains_tombstone_for_retry(self):
        self.disk = {"entry": record(pending=True)}
        self.publish.side_effect = OSError("broker unavailable")
        with self.assertRaises(OSError):
            await self.ledger.async_flush_removals(self.publish)
        self.assertTrue(self.disk["entry"]["pending"])
        self.publish.side_effect = None
        await self.ledger.async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})

    async def test_offline_state_is_persisted_and_flushed_after_restart(self):
        await self.ledger.async_prepare("entry", "coach", "homeassistant")
        await self.ledger.async_queue_offline("entry")
        restored = DiscoveryLedger(self.store)
        self.publish.side_effect = OSError("broker unavailable")
        with self.assertRaises(OSError):
            await restored.async_flush_offline(self.publish)
        self.assertTrue(self.disk["entry"]["pending_offline"])

        self.publish.side_effect = None
        await DiscoveryLedger(self.store).async_flush_offline(self.publish)
        self.assertFalse(self.disk["entry"]["pending_offline"])
        self.publish.assert_any_await(
            "vehicle/coach/j1939/availability", "offline", True
        )
        self.publish.assert_any_await(
            "vehicle/coach/j1587/availability", "offline", True
        )

    async def test_unrelated_active_record_is_not_removed(self):
        self.disk = {
            "old": record(pending=True),
            "active": {**record(), "vehicle_id": "other"},
        }
        await self.ledger.async_flush_removals(self.publish)
        self.assertEqual(list(self.disk), ["active"])
        self.assertFalse(any(
            "other" in call.args[0]
            for call in self.publish.await_args_list
        ))

    async def test_no_metadata_means_no_guessed_broker_topic_cleanup(self):
        await self.ledger.async_queue_removal("unknown")
        await self.ledger.async_flush_removals(self.publish)
        self.publish.assert_not_awaited()

    async def test_stored_identities_cannot_select_arbitrary_topics(self):
        self.disk = {
            "wildcard": record(prefix="ha/#"),
            "invalid": {**record(), "vehicle_id": "../other"},
            "malformed": None,
            "signals": record(
                signals=[[0, 190], [255, 190], [True, 190],
                         [0, 999999], [], "malformed"],
                pending=True,
            ),
        }
        await self.ledger.async_flush_removals(self.publish)
        deleted = [
            call.args[0] for call in self.publish.await_args_list
            if call.args[1] == "" and call.args[0].endswith("/config")
        ]
        self.assertEqual(deleted, [
            "homeassistant/binary_sensor/"
            "bluefire_coach_j1939_connectivity/config",
            "homeassistant/sensor/bluefire_coach_j1939_last_data/config",
            "homeassistant/sensor/bluefire_coach_0_190/config",
            "homeassistant/binary_sensor/"
            "bluefire_coach_j1587_connectivity/config",
            "homeassistant/sensor/bluefire_coach_j1587_last_data/config",
        ])


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.home_assistant_error = type(
            "HomeAssistantError", (Exception,), {}
        )
        modules = patch.dict(sys.modules, {
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                HomeAssistantError=self.home_assistant_error,
            ),
        })
        modules.start()
        self.addCleanup(modules.stop)

    async def test_cleanup_waits_for_broker_subscription_before_publish(self):
        received = None
        ready_callback = None
        broker_ready = False
        monitored = asyncio.Event()
        unsubscribe = Mock()
        stop_monitoring = Mock()

        async def subscribe(hass, topic, callback, qos):
            nonlocal received
            received = callback
            return unsubscribe

        def on_subscribe_done(hass, topic, qos, callback):
            nonlocal ready_callback
            ready_callback = callback
            monitored.set()
            return stop_monitoring

        async def publish(hass, topic, payload, **kwargs):
            if broker_ready:
                received(SimpleNamespace(payload=""))

        mqtt = SimpleNamespace(
            async_subscribe=subscribe,
            async_on_subscribe_done=Mock(side_effect=on_subscribe_done),
            async_publish=AsyncMock(side_effect=publish),
        )
        with patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", mqtt=mqtt
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func
            ),
        }):
            task = asyncio.create_task(async_confirm_removal(
                object(), "ha/sensor/test/config"
            ))
            try:
                await asyncio.wait_for(monitored.wait(), 1)
                mqtt.async_publish.assert_not_awaited()
                self.assertFalse(task.done())
                broker_ready = True
                ready_callback()
                ready_callback()
                await asyncio.wait_for(task, 1)
                mqtt.async_publish.assert_awaited_once()
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        unsubscribe.assert_called_once()
        stop_monitoring.assert_called_once()

    async def test_cleanup_requires_broker_echo_and_unsubscribes(self):
        received = None
        unsubscribe = Mock()

        async def subscribe(hass, topic, callback, qos):
            nonlocal received
            received = callback
            return unsubscribe

        async def publish(hass, topic, payload, **kwargs):
            received(SimpleNamespace(payload="other"))
            received(SimpleNamespace(payload=""))

        mqtt = SimpleNamespace(
            async_subscribe=subscribe, async_publish=AsyncMock(
                side_effect=publish
            ),
            async_on_subscribe_done=Mock(
                side_effect=lambda hass, topic, qos, cb: cb() or Mock()
            ),
        )
        with patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", mqtt=mqtt
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func
            ),
        }):
            await async_confirm_removal(object(), "ha/sensor/test/config")
        unsubscribe.assert_called_once()

    async def test_normal_publish_return_without_echo_does_not_confirm(self):
        subscribed = asyncio.Event()
        unsubscribe = Mock()

        async def subscribe(hass, topic, callback, qos):
            subscribed.set()
            return unsubscribe

        mqtt = SimpleNamespace(
            async_subscribe=subscribe,
            async_on_subscribe_done=Mock(
                side_effect=lambda hass, topic, qos, cb: cb() or Mock()
            ),
            # Models HA's normal return even after an ACK timeout.
            async_publish=AsyncMock(),
        )
        with patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", mqtt=mqtt
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func
            ),
        }):
            task = asyncio.create_task(async_confirm_removal(
                object(), "ha/sensor/test/config"
            ))
            await subscribed.wait()
            await asyncio.sleep(0)
            mqtt.async_publish.assert_awaited_once()
            self.assertFalse(task.done())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        unsubscribe.assert_called_once()

    async def test_confirmation_timeouts_report_topic_and_failed_phase(self):
        for phase in (
            "subscription readiness", "deletion publish", "deletion echo",
        ):
            with self.subTest(phase=phase):
                unsubscribe = Mock()
                stop_monitoring = Mock()
                ready_callback = None
                received = None
                topic = "vehicle/coach/j1587/191/pid/250"

                async def subscribe(hass, topic, callback, qos):
                    nonlocal received
                    received = callback
                    return unsubscribe

                def on_subscribe_done(hass, topic, qos, callback):
                    nonlocal ready_callback
                    ready_callback = callback
                    if phase != "subscription readiness":
                        callback()
                    # A message before our publish is not confirmation.
                    received(SimpleNamespace(payload=""))
                    return stop_monitoring

                async def publish(hass, topic, payload, **kwargs):
                    if phase == "deletion publish":
                        await asyncio.Future()

                mqtt = SimpleNamespace(
                    async_subscribe=subscribe,
                    async_on_subscribe_done=on_subscribe_done,
                    async_publish=AsyncMock(side_effect=publish),
                )
                with (
                    patch.dict(sys.modules, {
                        "homeassistant": module("homeassistant"),
                        "homeassistant.components": module(
                            "homeassistant.components", mqtt=mqtt,
                        ),
                        "homeassistant.core": module(
                            "homeassistant.core", callback=lambda func: func,
                        ),
                    }),
                    patch(
                        "custom_components.bluefire.mqtt."
                        "REMOVAL_CONFIRM_TIMEOUT", 0.02,
                    ),
                    self.assertRaisesRegex(
                        self.home_assistant_error, f"{phase}.*{topic}",
                    ),
                ):
                    await async_confirm_removal(object(), topic)
                unsubscribe.assert_called_once()
                stop_monitoring.assert_called_once()
                if phase == "subscription readiness":
                    mqtt.async_publish.assert_not_awaited()
                else:
                    mqtt.async_publish.assert_awaited_once()
                # Already scheduled callbacks may run after unsubscription.
                ready_callback()
                received(SimpleNamespace(payload=""))

    async def test_cancellation_before_readiness_cleans_up_both_listeners(
        self,
    ):
        monitored = asyncio.Event()
        unsubscribe = Mock()
        stop_monitoring = Mock()
        ready_callback = None

        def on_subscribe_done(hass, topic, qos, callback):
            nonlocal ready_callback
            ready_callback = callback
            monitored.set()
            return stop_monitoring

        mqtt = SimpleNamespace(
            async_subscribe=AsyncMock(return_value=unsubscribe),
            async_on_subscribe_done=on_subscribe_done,
            async_publish=AsyncMock(),
        )
        with patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", mqtt=mqtt,
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func,
            ),
        }):
            task = asyncio.create_task(async_confirm_removal(
                object(), "ha/sensor/test/config",
            ))
            await asyncio.wait_for(monitored.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            ready_callback()
        mqtt.async_publish.assert_not_awaited()
        unsubscribe.assert_called_once()
        stop_monitoring.assert_called_once()

    async def test_failed_subscription_does_not_publish_or_monitor(self):
        mqtt = SimpleNamespace(
            async_subscribe=AsyncMock(
                side_effect=self.home_assistant_error("subscription failed"),
            ),
            async_on_subscribe_done=Mock(),
            async_publish=AsyncMock(),
        )
        with (
            patch.dict(sys.modules, {
                "homeassistant": module("homeassistant"),
                "homeassistant.components": module(
                    "homeassistant.components", mqtt=mqtt,
                ),
                "homeassistant.core": module(
                    "homeassistant.core", callback=lambda func: func,
                ),
            }),
            self.assertRaisesRegex(
                self.home_assistant_error, "subscription failed",
            ),
        ):
            await async_confirm_removal(object(), "ha/sensor/test/config")
        mqtt.async_on_subscribe_done.assert_not_called()
        mqtt.async_publish.assert_not_awaited()
