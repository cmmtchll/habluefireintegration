"""Exercise the transport-independent contract without HA or BLE hardware."""

import json
import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.bluefire.protocol import (
    AdapterMessage,
    PgnReport,
)
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
            (65262, "64 ff a0 2e ff ff ff ff",
             {110: 60, 175: 100, 174: None, 176: None, 52: None}),
            (65263, "ff ff ff 32 ff ff 19 7d",
             {100: 200, 109: 50, 111: 50, 94: None, 98: None}),
            (65265, "ff 00 32 ff ff ff ff ff", {84: 50}),
            (65266, "c8 00 ff ff ff ff ff ff", {183: 10}),
            (65253, "20 4e 00 00 ff ff ff ff", {247: 1000}),
            (65248, "ff ff ff ff 40 1f 00 00", {245: 1000}),
            (65271, "ff ff ff ff e0 01 ff ff", {168: 24, 167: None}),
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
                    self.assertIsNone(signal.decode(bytes(data)))

    def test_zero_and_negative_values_are_valid(self):
        signals = {signal.spn: signal for signal in SIGNALS}
        self.assertEqual(signals[190].decode(bytes(8)), 0)
        self.assertEqual(signals[110].decode(bytes(8)), -40)
        self.assertEqual(signals[513].decode(bytes(8)), -125)

    def test_additional_signal_fixtures(self):
        fixtures = (
            (65276, 96, "ff 7d ff ff ff ff ff ff", 50),
            (65269, 108, "c8 ff ff ff ff ff ff ff", 100),
            (65269, 171, "ff ff ff a0 24 ff ff ff", 20),
            (65269, 172, "ff ff ff ff ff 3c ff ff", 20),
            (65270, 102, "ff 64 ff ff ff ff ff ff", 200),
            (65270, 105, "ff ff 50 ff ff ff ff ff", 40),
            (65270, 106, "ff ff ff 32 ff ff ff ff", 100),
            (65270, 107, "ff ff ff ff 14 ff ff ff", 1),
            (65270, 173, "ff ff ff ff ff a0 60 ff", 500),
            (65272, 124, "ff 7d ff ff ff ff ff ff", 50),
            (65272, 126, "ff ff 05 ff ff ff ff ff", 10),
            (65272, 127, "ff ff ff 64 ff ff ff ff", 1600),
            (65272, 177, "ff ff ff ff 60 2d ff ff", 90),
            (65257, 182, "c8 00 00 00 ff ff ff ff", 100),
            (65257, 250, "ff ff ff ff 20 4e 00 00", 10000),
            (65244, 236, "d0 07 00 00 ff ff ff ff", 1000),
            (65244, 235, "ff ff ff ff 20 4e 00 00", 1000),
            (65271, 167, "ff ff 1c 02 ff ff ff ff", 27),
            (65263, 94, "32 ff ff ff ff ff ff ff", 200),
            (65263, 98, "ff ff 7d ff ff ff ff ff", 50),
            (65262, 174, "ff 46 ff ff ff ff ff ff", 30),
            (65262, 176, "ff ff ff ff a0 2e ff ff", 100),
            (65262, 52, "ff ff ff ff ff ff 50 ff", 40),
        )
        for pgn, spn, data, expected in fixtures:
            with self.subTest(pgn=pgn, spn=spn):
                signal = next(
                    item for item in SIGNALS
                    if item.pgn == pgn and item.spn == spn
                )
                self.assertEqual(signal.decode(bytes.fromhex(data)), expected)
        original = {
            190, 513, 91, 92, 110, 175, 100, 109, 111,
            84, 183, 247, 245, 168,
        }
        self.assertEqual(
            original | {spn for _, spn, _, _ in fixtures},
            {signal.spn for signal in SIGNALS},
        )

    def test_numeric_valid_range_boundaries(self):
        for signal in SIGNALS:
            first_invalid = 0xFB << (8 * (signal.length - 1))
            for raw, valid in (
                (0, True),
                (first_invalid - 1, True),
                (first_invalid, False),
                ((1 << (8 * signal.length)) - 1, False),
            ):
                with self.subTest(spn=signal.spn, raw=raw):
                    data = bytearray([0xFF] * 8)
                    end = signal.start + signal.length
                    data[signal.start:end] = raw.to_bytes(
                        signal.length, "little"
                    )
                    value = signal.decode(bytes(data))
                    if valid:
                        self.assertAlmostEqual(
                            value, raw * signal.resolution + signal.offset,
                            places=5,
                        )
                    else:
                        self.assertIsNone(value)

    def test_catalog_layout_and_unique_identities(self):
        self.assertEqual(
            len({(s.pgn, s.spn) for s in SIGNALS}), len(SIGNALS)
        )
        for signal in SIGNALS:
            with self.subTest(spn=signal.spn):
                self.assertIn(signal.length, (1, 2, 4))
                self.assertGreaterEqual(signal.start, 0)
                self.assertLessEqual(signal.start + signal.length, 8)
                self.assertGreater(signal.resolution, 0)
                self.assertEqual(
                    signal.decode(bytes(8)), signal.offset
                )

    def test_incomplete_reports_cannot_become_plausible_measurements(self):
        for signal in SIGNALS:
            for length in range(8):
                with self.subTest(spn=signal.spn, length=length):
                    with self.assertRaises(ValueError):
                        signal.decode(bytes(length))
            for data in (bytes(9), bytearray(8), "abcdefgh", None):
                with self.subTest(spn=signal.spn, data=data):
                    with self.assertRaises(ValueError):
                        signal.decode(data)


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
                ("vehicle/coach/j1587/availability", "offline", True),
                ("vehicle/coach/j1939/availability", "offline", True)])

    async def test_vendor_reports_cannot_enter_the_can_frame_contract(self):
        for report in (
            PgnReport(0, 61444, 6, 0, bytes(8)),
            AdapterMessage(255, b""),
            bytes(8),
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                await self.bridge.async_process_frame(report)
        self.publish.assert_not_awaited()

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
            messages[-1], (self.bridge.availability_topic, "online", True))

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

    async def test_raw_frame_preserves_can_envelope_and_payload(self):
        value = Frame(0x18EA8003, bytes.fromhex("01 02 03 04 05 06 07 08"))
        await self.bridge.async_process_frame(value)
        raw = json.loads(self.messages()[0][1])
        self.assertEqual(raw["arbitration_id"], value.can_id)
        self.assertEqual(raw["can_id"], value.can_id)
        self.assertTrue(raw["is_extended_id"])
        self.assertEqual(raw["dlc"], 8)
        self.assertEqual(raw["source_address"], 3)
        self.assertEqual(raw["priority"], 6)
        self.assertEqual(raw["pgn"], 59904)
        self.assertEqual(raw["data"], "0102030405060708")

    async def test_not_available_replaces_previous_measurement_with_null(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        payload = next(payload for topic, payload,
                       _ in self.messages() if topic.endswith("/spn/190"))
        self.assertEqual(json.loads(payload)["value"], 1000)
        config = json.loads(next(
            payload for topic, payload, _ in self.messages()
            if topic.endswith("_190/config")
        ))
        self.publish.reset_mock()
        await self.bridge.async_process_frame(
            frame(61444, "ff ff ff ff ff ff ff ff")
        )
        payload = next(payload for topic, payload,
                       _ in self.messages() if topic.endswith("/spn/190"))
        self.assertIsNone(json.loads(payload)["value"])
        # MQTT numeric sensors treat "None" as unknown but ignore empty text,
        # which would retain stale readings while resetting their expiry timer.
        self.assertEqual(
            config["value_template"],
            "{{ value_json.value if value_json.value "
            "is not none else 'None' }}",
        )

    async def test_invalid_values_do_not_reuse_another_sources_reading(self):
        await self.bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff", source=0)
        )
        for marker in range(0xFB, 0x100):
            for source in (0, 3):
                self.publish.reset_mock()
                data = bytes((255, 255, 125, 0, marker, 255, 255, 255))
                await self.bridge.async_process_frame(
                    Frame((6 << 26) | (61444 << 8) | source, data)
                )
                topic, payload, retain = next(
                    message for message in self.messages()
                    if message[0].endswith("/spn/190")
                )
                with self.subTest(marker=marker, source=source):
                    self.assertEqual(
                        topic, f"vehicle/coach/j1939/{source}/spn/190"
                    )
                    state = json.loads(payload)
                    self.assertIsNone(state["value"])
                    self.assertEqual(state["source_address"], source)
                    self.assertFalse(retain)

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
            self.messages()[1],
            (self.bridge.availability_topic,
             "offline",
             True))
        self.assertTrue(all(payload == "" and retain for _,
                        payload, retain in self.messages()[2:]))

    async def test_every_signal_publishes_state_and_discovery_metadata(self):
        for pgn in {signal.pgn for signal in SIGNALS}:
            await self.bridge.async_process_frame(
                Frame((6 << 26) | (pgn << 8) | 3, bytes(8))
            )
        messages = {
            topic: (payload, retain)
            for topic, payload, retain in self.messages()
        }
        for signal in SIGNALS:
            with self.subTest(spn=signal.spn):
                key = f"bluefire_coach_3_{signal.spn}"
                config, retain = messages[
                    f"homeassistant/sensor/{key}/config"
                ]
                config = json.loads(config)
                self.assertTrue(retain)
                self.assertEqual(config["state_class"], signal.state_class)
                self.assertEqual(
                    config.get("device_class"), signal.device_class
                )
                self.assertEqual(config["unit_of_measurement"], signal.unit)
                payload, retain = messages[config["state_topic"]]
                state = json.loads(payload)
                self.assertFalse(retain)
                self.assertEqual(state["value"], signal.offset)
                self.assertEqual(state["pgn"], signal.pgn)
                self.assertEqual(state["source_address"], 3)
                self.assertEqual(state["unit"], signal.unit)

    async def test_availability_retained_only_on_transition(self):
        value = frame(61444, "ff ff 7d 40 1f ff ff ff")
        await self.bridge.async_process_frame(value)
        await self.bridge.async_process_frame(value)
        availability = [
            (payload, retain) for topic, payload, retain in self.messages()
            if topic == self.bridge.availability_topic
        ]
        self.assertEqual(availability, [("online", True)])
        await self.bridge.async_disconnected()
        self.assertEqual(
            self.messages()[-1],
            (self.bridge.availability_topic, "offline", True),
        )

    async def test_watchdog_expires_stream_and_new_frame_restores_online(self):
        clock = Mock(return_value=100)
        bridge = MqttBridge("coach", self.publish, clock=clock)
        value = frame(61444, "ff ff 7d 40 1f ff ff ff")
        await bridge.async_check_stale()
        self.publish.assert_not_awaited()
        await bridge.async_process_frame(value)
        self.publish.reset_mock()
        clock.return_value = 159
        await bridge.async_check_stale()
        self.publish.assert_not_awaited()
        clock.return_value = 160
        await bridge.async_check_stale()
        self.assertEqual(self.messages(), [
            (bridge.availability_topic, "offline", True),
        ])
        await bridge.async_check_stale()
        self.assertEqual(len(self.messages()), 1)
        await bridge.async_process_frame(value)
        self.assertEqual(
            self.messages()[-1], (bridge.availability_topic, "online", True)
        )

    async def test_discovery_survives_restart_without_measurement_replay(self):
        save = AsyncMock()
        bridge = MqttBridge("coach", self.publish, save_discovery=save)
        await bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        saved = save.await_args.args[0]
        self.assertEqual(saved, [[0, 190], [0, 513]])
        self.publish.reset_mock()
        restored = MqttBridge(
            "coach", self.publish, known_signals=saved,
            device_name="Coach adapter",
        )
        await restored.async_disconnected()
        await restored.async_rediscover()
        self.assertEqual(len(self.messages()), 4)
        self.assertEqual(self.messages()[0][1], "offline")
        for topic, payload, retain in self.messages()[2:]:
            self.assertTrue(topic.endswith("/config"))
            self.assertEqual(
                json.loads(payload)["device"]["name"], "Coach adapter"
            )
            self.assertTrue(retain)

    async def test_ownership_is_saved_before_retained_discovery_publish(self):
        save = AsyncMock(side_effect=OSError("disk full"))
        bridge = MqttBridge("coach", self.publish, save_discovery=save)
        with self.assertRaises(OSError):
            await bridge.async_process_frame(
                frame(61444, "ff ff 7d 40 1f ff ff ff")
            )
        self.assertFalse(any(
            topic.endswith("/config") for topic, _, _ in self.messages()
        ))
        self.assertEqual(bridge.discovery, {})

    async def test_restored_definitions_are_removed_and_storage_cleared(self):
        save = AsyncMock()
        bridge = MqttBridge(
            "coach", self.publish,
            known_signals=[[0, 190], [3, 190]], save_discovery=save,
        )
        await bridge.async_remove_discovery()
        self.assertEqual(len(self.messages()), 4)
        self.assertTrue(all(
            payload == "" and retain
            for _, payload, retain in self.messages()[2:]
        ))
        save.assert_awaited_once_with([])
        self.assertEqual(bridge.discovery, {})

    async def test_discovery_prefix_does_not_change_state_topics(self):
        bridge = MqttBridge(
            "coach", self.publish, discovery_prefix="ha/custom"
        )
        await bridge.async_process_frame(
            frame(61444, "ff ff 7d 40 1f ff ff ff")
        )
        self.assertTrue(any(
            topic == "ha/custom/sensor/bluefire_coach_0_190/config"
            for topic, _, _ in self.messages()
        ))
        self.assertTrue(any(
            topic == "vehicle/coach/j1939/0/spn/190"
            for topic, _, _ in self.messages()
        ))

    async def test_non_transmitter_addresses_do_not_create_entities(self):
        for source in (254, 255):
            await self.bridge.async_process_frame(
                frame(61444, "ff ff 7d 40 1f ff ff ff", source=source)
            )
        self.publish.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
