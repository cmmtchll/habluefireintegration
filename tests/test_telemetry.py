"""Exercise the transport-independent contract without HA or BLE hardware."""

import json
import unittest
from unittest.mock import AsyncMock

from custom_components.bluefire.telemetry import (
    Frame,
    MqttBridge,
    SIGNALS,
    valid_vehicle_id,
)


def frame(pgn, data, source=0):
    return Frame((6 << 26) | (pgn << 8) | source, bytes.fromhex(data))


class FrameTests(unittest.TestCase):
    def test_identifier_fields(self):
        value = frame(61444, "ff ff 7d 40 1f ff ff ff", source=3)
        self.assertEqual(value.pgn, 61444)
        self.assertEqual(value.source_address, 3)
        self.assertEqual(value.priority, 6)

    def test_pdu1_destination_is_not_part_of_pgn(self):
        self.assertEqual(Frame(0x18EA8003, bytes(8)).pgn, 59904)

    def test_data_page_is_preserved(self):
        self.assertEqual(Frame(0x19F00103, bytes(8)).pgn, 0x1F001)
        self.assertEqual(Frame(0x19EA8003, bytes(8)).pgn, 0x1EA00)

    def test_malformed_frames_are_rejected(self):
        for can_id in (-1, 0x20000000, 1.0, True):
            with self.subTest(can_id=can_id), self.assertRaises(ValueError):
                Frame(can_id, bytes(8))
        for data in (b"", bytes(7), bytes(9), bytearray(8), "abcdefgh"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Frame(0, data)

    def test_topic_identifier_validation(self):
        for value in ("liberty_h3_45", "coach-1", "a", "0"):
            self.assertTrue(valid_vehicle_id(value))
        for value in (
            "",
            "+",
            "#",
            "/coach",
            "a/b",
            "Coach",
            "_coach",
            "a" * 65,
            "a\n",
        ):
            self.assertFalse(valid_vehicle_id(value))
            with self.assertRaises(ValueError):
                MqttBridge(value, AsyncMock())


class DecodeTests(unittest.TestCase):
    def test_known_engineering_values(self):
        fixtures = (
            (61444, "ff ff 7d 40 1f ff ff ff", {190: 1000, 513: 0}),
            (61443, "ff 7d 32 ff ff ff ff ff", {91: 50, 92: 50}),
            (65262, "64 ff a0 2e ff ff ff ff", {110: 60, 175: 100}),
            (65263, "ff ff ff 32 ff ff 19 7d", {100: 200, 109: 50, 111: 50}),
            (65265, "ff 00 32 ff ff ff ff ff", {84: 50}),
            (65266, "c8 00 ff ff ff ff ff ff", {183: 10}),
            (65253, "20 4e 00 00 ff ff ff ff", {247: 1000}),
            (65248, "ff ff ff ff 40 1f 00 00", {245: 1000}),
            (65271, "ff ff ff ff e0 01 ff ff", {168: 24}),
        )
        for pgn, data, expected in fixtures:
            with self.subTest(pgn=pgn):
                actual = {
                    signal.spn: signal.decode(bytes.fromhex(data))
                    for signal in SIGNALS
                    if signal.pgn == pgn
                }
                self.assertEqual(actual, expected)

    def test_all_invalid_ranges_are_missing_not_zero(self):
        for signal in SIGNALS:
            for marker in range(0xFB, 0x100):
                data = bytearray(8)
                data[signal.start + signal.length - 1] = marker
                with self.subTest(spn=signal.spn, marker=marker):
                    self.assertIsNone(signal.decode(data))

    def test_zero_and_negative_values_are_valid(self):
        signals = {signal.spn: signal for signal in SIGNALS}
        self.assertEqual(signals[190].decode(bytes(8)), 0)
        self.assertEqual(signals[110].decode(bytes(8)), -40)
        self.assertEqual(signals[513].decode(bytes(8)), -125)


class PublishingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.publish = AsyncMock()
        self.bridge = MqttBridge("coach", self.publish)

    def messages(self):
        return [call.args for call in self.publish.await_args_list]

    async def test_no_telemetry_before_a_frame(self):
        await self.bridge.async_disconnected()
        self.assertEqual(
            self.messages(), [
                ("vehicle/coach/j1939/availability", "offline", True)])

    async def test_discovery_and_unit_explicit_state(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        messages = self.messages()
        config = json.loads(next(payload for topic, payload,
                            _ in messages if topic.endswith("_190/config")))
        self.assertEqual(config["unit_of_measurement"], "rpm")
        self.assertEqual(config["expire_after"], 60)
        topic, payload, retain = next(
            message for message in messages if message[0].endswith("/spn/190"))
        self.assertEqual(topic, "vehicle/coach/j1939/0/spn/190")
        state = json.loads(payload)
        self.assertEqual(state["value"], 1000)
        self.assertEqual(state["spn"], 190)
        self.assertEqual(state["pgn"], 61444)
        self.assertEqual(state["source_address"], 0)
        self.assertEqual(state["protocol"], "j1939")
        self.assertEqual(state["unit"], "rpm")
        self.assertTrue(state["timestamp"].endswith("+00:00"))
        self.assertFalse(retain)
        self.assertEqual(
            messages[-1], (self.bridge.availability_topic, "online", False))

    async def test_discovery_once_per_source_and_spn(self):
        value = frame(61444, "ff ff 7d 40 1f ff ff ff")
        await self.bridge.async_process_frame(value)
        await self.bridge.async_process_frame(value)
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff", source=3)
        )
        configs = [topic for topic, _,
                   _ in self.messages() if topic.endswith("/config")]
        self.assertEqual(len(configs), 4)
        self.assertEqual(len(set(configs)), 4)

    async def test_unknown_pgn_is_preserved_without_guessing(self):
        await self.bridge.async_process_frame(
            frame(65000, "01 02 03 04 05 06 07 08")
        )
        messages = self.messages()
        self.assertEqual(len(messages), 2)
        raw = json.loads(messages[0][1])
        self.assertEqual(raw["data"], "0102030405060708")
        self.assertEqual(raw["pgn"], 65000)
        self.assertFalse(messages[0][2])

    async def test_not_available_replaces_previous_measurement_with_null(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff ff ff ff ff ff ff")
        )
        payload = next(payload for topic, payload,
                       _ in self.messages() if topic.endswith("/spn/190"))
        self.assertIsNone(json.loads(payload)["value"])
        config = json.loads(next(
            payload for topic, payload, _ in self.messages()
            if topic.endswith("_190/config")
        ))
        # MQTT numeric sensors treat "None" as unknown but ignore empty text,
        # which would retain stale readings while resetting their expiry timer.
        self.assertEqual(
            config["value_template"],
            "{{ value_json.value if value_json.value "
            "is not none else 'None' }}",
        )

    async def test_rediscovery_never_replays_old_measurements(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        self.publish.reset_mock()
        await self.bridge.async_rediscover()
        self.assertEqual(len(self.messages()), 2)
        self.assertTrue(all(topic.endswith("/config")
                        and retain for topic, _, retain in self.messages()))

    async def test_discovery_failure_is_retryable(self):
        self.publish.side_effect = [None, RuntimeError("broker unavailable")]
        with self.assertRaises(RuntimeError):
            await self.bridge.async_process_frame(
                frame(61444, "ff ff 7d 40 1f ff ff ff")
            )
        self.assertEqual(self.bridge.discovery, {})
        self.publish.side_effect = None
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        self.assertEqual(len(self.bridge.discovery), 2)

    async def test_remove_discovery_clears_retained_definitions(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        self.publish.reset_mock()
        await self.bridge.async_remove_discovery()
        self.assertEqual(
            self.messages()[0],
            (self.bridge.availability_topic,
             "offline",
             True))
        self.assertTrue(all(payload == "" and retain for _,
                        payload, retain in self.messages()[1:]))


if __name__ == "__main__":
    unittest.main()
