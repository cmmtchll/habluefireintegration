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
        })

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

    async def test_failed_cleanup_retains_tombstone_for_retry(self):
        self.disk = {"entry": record(pending=True)}
        self.publish.side_effect = OSError("broker unavailable")
        with self.assertRaises(OSError):
            await self.ledger.async_flush_removals(self.publish)
        self.assertTrue(self.disk["entry"]["pending"])
        self.publish.side_effect = None
        await self.ledger.async_flush_removals(self.publish)
        self.assertEqual(self.disk, {})

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
            "homeassistant/sensor/bluefire_coach_0_190/config"
        ])


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
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
