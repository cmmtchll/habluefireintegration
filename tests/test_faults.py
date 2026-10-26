"""Synthetic diagnostic vectors; no hardware compatibility claim."""

from io import StringIO
import json
import unittest
from unittest.mock import AsyncMock

from custom_components.bluefire.faults import decode_diagnostics
from custom_components.bluefire.protocol import ProtocolError
from custom_components.bluefire.telemetry import (
    Frame, MqttBridge, validated_signal_ids,
)
from scripts.analyze_bluefire import analyze_capture


def dtc(spn, fmi, occurrence=1, conversion=0):
    return bytes((
        spn & 255, (spn >> 8) & 255,
        ((spn >> 16) << 5) | fmi, occurrence | (conversion << 7),
    ))


def packet(body):
    size = len(body)
    checksum = sum(body)
    while checksum > 255:
        checksum = (checksum & 255) + (checksum >> 8)
    return bytes((size >> 8, size & 255, (size >> 8) ^ (size & 255))) + \
        body + bytes((255 - checksum,))


class DiagnosticTests(unittest.TestCase):
    def decode(self, data, pgn=65226, source=0):
        return decode_diagnostics(pgn, data, source=source)

    def test_engine_transmission_brakes_and_body_keep_source_scoping(self):
        for source, spn, name in (
            (0, 100, "Engine oil pressure"),
            (3, 177, "Transmission oil temperature"),
            (11, 117, "Primary brake air pressure"),
            (33, 168, "Battery potential"),
        ):
            result = self.decode(
                b"\x04\xff" + dtc(spn, 1) + b"\xff\xff", source=source
            )
            self.assertEqual(result["fault_count"], 1)
            fault, = result["faults"]
            self.assertEqual(fault["spn"], spn)
            self.assertEqual(fault["name"], name)
            self.assertEqual(fault["failure_mode"],
                             "Below normal range (most severe)")
            self.assertEqual(fault["occurrence_count"], 1)
            self.assertEqual(fault["conversion_method"], 0)
            self.assertTrue(fault["known"])
            self.assertIsNone(fault["unit"])
            self.assertEqual(result["lamps"]["amber_warning"]["status"], "On")
            self.assertEqual(result["lamps"]["red_stop"]["status"], "Off")
            self.assertEqual(result["lamps"]["protect"]["flash"],
                             "Unavailable")

    def test_high_spn_bits_fmi_zero_and_missing_occurrence(self):
        result = self.decode(b"\x00\xff" + dtc(0x52345, 0, 127))
        fault, = result["faults"]
        self.assertEqual(fault["spn"], 0x52345)
        self.assertEqual(fault["fmi"], 0)
        self.assertIsNone(fault["occurrence_count"])
        self.assertFalse(fault["known"])
        self.assertIn("Unmapped SPN", result["summary"])

    def test_no_fault_unavailable_and_legacy_are_distinct(self):
        for pgn, summary in (
            (65226, "No active faults"), (65227, "No previously active faults")
        ):
            result = self.decode(b"\x00\xff" + bytes(4), pgn=pgn)
            self.assertEqual(result["summary"], summary)
            self.assertEqual(result["fault_count"], 0)
        result = self.decode(b"\xff" * 8)
        self.assertIsNone(result["fault_count"])
        self.assertEqual(result["decode_status"], "unavailable")
        result = self.decode(b"\x00\xff" + dtc(100, 1, conversion=1))
        self.assertEqual(result["decode_status"], "unsupported_conversion")
        self.assertIsNone(result["faults"][0]["spn"])
        self.assertNotIn("No active", result["summary"])
        self.assertEqual(result["fault_count"], 1)

    def test_reassembled_multiple_faults_and_independent_lamp_bitfields(self):
        result = self.decode(
            b"\xe4\x1b" + dtc(100, 1) + dtc(110, 0, 126)
        )
        self.assertEqual(result["summary"], "2 faults reported")
        self.assertEqual(result["faults"][1]["occurrence_count"], 126)
        for name, state, flash in (
            ("malfunction", "Unavailable", "Slow flash"),
            ("red_stop", "Reserved", "Fast flash"),
            ("amber_warning", "On", "Reserved"),
            ("protect", "Off", "Unavailable"),
        ):
            self.assertEqual(result["lamps"][name]["status"], state)
            self.assertEqual(result["lamps"][name]["flash"], flash)

    def test_malformed_diagnostics_cannot_report_no_faults(self):
        for source in (-1, 256, True):
            with self.assertRaises(ValueError):
                self.decode(b"\x00\xff" + bytes(4), source=source)
        for pgn, data in (
            (61444, bytes(8)), (65226, bytearray(8)),
            (65226, bytes(5)), (65226, bytes(7)),
            (65226, bytes(8)), (65226, bytes(9)),
            (65226, b"\x00\xff" + bytes(4) + dtc(100, 1)),
            (65226, b"\x00\xff" + b"\xff" * 4 + dtc(100, 1)),
        ):
            with self.subTest(pgn=pgn, data=data):
                with self.assertRaises(ValueError):
                    self.decode(data, pgn=pgn)

    def test_replay_uses_same_catalog_for_dm_and_other_namespaces(self):
        for pgn, payload in (
            (65226, b"\x04\xff" + dtc(100, 1) + b"\xff\xff"),
            (65227, b"\x00\xff" + dtc(100, 1) + dtc(110, 0)),
        ):
            body = bytes((
                151, 0, pgn >> 8, pgn & 255, 6, 0, len(payload),
            )) + payload
            record, = analyze_capture(
                StringIO(packet(body).hex()), padded_notifications=False
            )
            self.assertEqual(record["source_name"], "Engine")
            self.assertIn("diagnostic faults", record["pgn_name"])
            self.assertEqual(record["diagnostics"],
                             self.decode(payload, pgn=pgn))
        for pid in (12, 0x100):
            body = bytes((
                174, 7, 0xE8, 1, pid >> 8, pid & 255, 2, 0, 0,
            ))
            record, = analyze_capture(
                StringIO(packet(body).hex()), padded_notifications=False
            )
            self.assertEqual(record["parameter"]["known"], pid == 12)
        body = bytes((154, 128, 0, 190, 2, 0, 0))
        record, = analyze_capture(
            StringIO(packet(body).hex()), padded_notifications=False,
            j1587_extended=False,
        )
        self.assertEqual(record["parameter"]["name"], "Engine speed")
        self.assertEqual(record["source_name"], "Engine")
        body = bytes((151, 0, 0xFE, 0xCA, 6, 0, 1, 0))
        with self.assertRaisesRegex(ProtocolError, "Line 1: Incomplete"):
            list(analyze_capture(
                StringIO(packet(body).hex()), padded_notifications=False
            ))


class DiagnosticPublishingTests(unittest.IsolatedAsyncioTestCase):
    async def test_fault_discovery_ownership_replay_and_removal(self):
        publish, save = AsyncMock(), AsyncMock()
        bridge = MqttBridge("coach", publish, save_discovery=save)
        for source in (0, 3, 11, 33):
            for pgn in (65226, 65227):
                await bridge.async_process_frame(Frame(
                    (6 << 26) | (pgn << 8) | source,
                    b"\x04\xff" + dtc(100, 1) + b"\xff\xff",
                ))
        identities = save.await_args.args[0]
        self.assertEqual(len(identities), 8)
        self.assertEqual(validated_signal_ids(identities), identities)
        self.assertEqual(validated_signal_ids([[0, -123], [0, True]]), [])
        for topic, payload, retain in (
            call.args for call in publish.await_args_list
        ):
            if topic.endswith("/config"):
                config = json.loads(payload)
                self.assertTrue(retain)
                self.assertNotIn("unit_of_measurement", config)
                self.assertNotIn("state_class", config)
                self.assertIn(": ", config["name"])
                self.assertIn("faults", config["name"])
                self.assertNotIn("suggested_display_precision", config)
                self.assertEqual(config["entity_category"], "diagnostic")
                self.assertEqual(config["value_template"],
                                 "{{ value_json.summary }}")
                self.assertEqual(config["json_attributes_topic"],
                                 config["state_topic"])
            elif "/faults/" in topic:
                self.assertFalse(retain)
                self.assertEqual(json.loads(payload)["fault_count"], 1)
        publish.reset_mock()
        restored = MqttBridge("coach", publish, known_signals=identities)
        await restored.async_rediscover()
        self.assertEqual(publish.await_count, 12)
        self.assertTrue(all(
            call.args[0].endswith("/config")
            for call in publish.await_args_list
        ))
        publish.reset_mock()
        await restored.async_remove_discovery()
        self.assertEqual(sum(
            payload == "" for _, payload, _ in (
                call.args for call in publish.await_args_list
            )
        ), 14)

    async def test_fault_clear_and_na_replace_state(self):
        publish, save = AsyncMock(), AsyncMock()
        bridge = MqttBridge("coach", publish, save_discovery=save)
        can_id = (6 << 26) | (65226 << 8)
        for payload in (
            b"\x00\xff" + dtc(100, 1) + b"\xff\xff",
            b"\x00\xff" + bytes(4) + b"\xff\xff",
            b"\xff" * 8,
        ):
            await bridge.async_process_frame(Frame(can_id, payload))
        states = [
            json.loads(call.args[1])
            for call in publish.await_args_list
            if call.args[0].endswith("/faults/65226")
        ]
        self.assertEqual([s["fault_count"] for s in states], [1, 0, None])
        save.assert_awaited_once_with([[0, -65226]])
        self.assertEqual(sum(
            call.args[0].endswith("/config")
            for call in publish.await_args_list
        ), 1)
        publish.reset_mock()
        with self.assertRaises(ValueError):
            await bridge.async_process_frame(Frame(can_id, bytes(8)))
        publish.assert_not_awaited()
