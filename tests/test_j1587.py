"""J1708/J1587 synthetic vectors, conversions and protocol isolation."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.bluefire.catalog import export_catalog
from custom_components.bluefire.j1587 import (
    IDENTIFICATION_PARAMETERS, PARAMETERS, READABLE_PIDS, STATUS_PARAMETERS,
    decode_faults, decode_report, parse_j1708_message,
)
from custom_components.bluefire.protocol import J1587Report, ProtocolError
from custom_components.bluefire.telemetry import (
    Frame, MqttBridge, validated_j1587_ids,
)
from scripts.analyze_bluefire import analyze_capture, analyze_j1708, main


def datagram(*data):
    return bytes((*data, (-sum(data)) & 255))


def packet(body):
    total = sum(body)
    while total > 255:
        total = (total & 255) + (total >> 8)
    return bytes((len(body) >> 8, len(body) & 255,
                  (len(body) >> 8) ^ (len(body) & 255))) + \
        body + bytes((255 - total,))


class ParameterTests(unittest.TestCase):
    def test_identification_text_is_reported_not_inferred(self):
        for parameter, data in zip(IDENTIFICATION_PARAMETERS, (
            b"ECU SOFTWARE EXAMPLE*REV A",
            b"EXAMPLE VIN",
            b"EXAMPLE MAKE*EXAMPLE MODEL*EXAMPLE SERIAL*",
        )):
            with self.subTest(pid=parameter.pid):
                result = decode_report(J1587Report(128, parameter.pid, data))
                self.assertTrue(result["value_decoded"])
                value = result["identification"]
                self.assertEqual(value["value"], data.decode("ascii"))
                self.assertEqual(value["decode_status"], "decoded")
                self.assertEqual(
                    value["identity_basis"], "controller_reported"
                )
                self.assertEqual(value["data"], data.hex())
                self.assertEqual(value["name"], parameter.name)
                self.assertNotIn("profile", value)
        for data, status in (
            (b"", "unavailable"), (b"\xff\xff", "unavailable"),
            (b"   ", "unavailable"), (b"\x01ABC", "unsupported_encoding"),
            (b"ABC\xff", "unsupported_encoding"),
            (b"ABC\x00", "unsupported_encoding"),
        ):
            with self.subTest(data=data):
                result = decode_report(J1587Report(128, 243, data))
                self.assertFalse(result["value_decoded"])
                self.assertIsNone(result["identification"]["value"])
                self.assertEqual(
                    result["identification"]["decode_status"], status
                )
                self.assertEqual(result["identification"]["data"], data.hex())
        self.assertEqual(
            decode_report(J1587Report(128, 243, b" A "))[
                "identification"]["value"],
            "A",
        )

    def test_independent_scaling_and_canonical_units(self):
        fixtures = (
            (26, 100, 50, "%"), (68, 100, 50, "%"),
            (74, 100, 80.4672, "km/h"), (86, 100, 80.4672, "km/h"),
            (122, 100, 50, "%"),
            (184, 256, 0.425144, "km/L"), (185, 256, 0.425144, "km/L"),
            (439, 800, 100, "kPa"),
            (51, 125, 50, "%"),
            (84, 100, 80.4672, "km/h"),
            (91, 125, 50, "%"), (92, 100, 50, "%"),
            (94, 100, 344.737865, "kPa"),
            (96, 100, 50, "%"), (100, 100, 344.737865, "kPa"),
            (101, 16, 13.789515, "kPa"), (102, 80, 68.947573, "kPa"),
            (105, 32, 0, "°C"), (110, 212, 100, "°C"),
            (108, 232, 99.973981, "kPa"), (109, 80, 68.947573, "kPa"),
            (111, 100, 50, "%"),
            (116, 200, 827.370875, "kPa"),
            (117, 200, 827.370875, "kPa"),
            (118, 200, 827.370875, "kPa"),
            (120, 106, 100, "°C"),
            (171, 848, 100, "°C"), (172, 848, 100, "°C"),
            (173, 848, 100, "°C"), (175, 848, 100, "°C"),
            (177, 848, 100, "°C"),
            (168, 480, 24, "V"), (183, 64, 3.785412, "L/h"),
            (190, 4000, 1000, "rpm"), (235, 20000, 1000, "h"),
            (236, 8, 3.785412, "L"), (245, 10, 1.609344, "km"),
            (247, 20000, 1000, "h"), (250, 8, 3.785412, "L"),
        )
        self.assertEqual({p.pid for p in PARAMETERS},
                         {pid for pid, *_ in fixtures})
        self.assertEqual(len(PARAMETERS), 39)
        for pid, raw, expected, unit in fixtures:
            definition = next(p for p in PARAMETERS if p.pid == pid)
            result = decode_report(J1587Report(
                128, pid, raw.to_bytes(definition.length, "little")
            ))
            signal, = result["signals"]
            self.assertTrue(result["value_decoded"])
            self.assertEqual(signal["value"], expected)
            self.assertEqual(signal["unit"], unit)
            self.assertNotIn("spn", signal)
        self.assertEqual(
            len(export_catalog()["j1587_measurements"]), len(PARAMETERS)
        )

    def test_unavailable_zero_and_negative_temperature(self):
        for parameter in PARAMETERS:
            unavailable = parameter.decode(b"\xff" * parameter.length)
            self.assertIsNone(unavailable)
            self.assertAlmostEqual(
                parameter.decode(bytes(parameter.length)), parameter.offset,
                places=6,
            )
            # J1939's 0xFB invalid-range rule is not applied to J1587.
            self.assertIsNotNone(parameter.decode(
                bytes([0xFE] * parameter.length)
            ))
            for length in (parameter.length - 1, parameter.length + 1):
                with self.assertRaises(ValueError):
                    parameter.decode(bytes(length))
            with self.assertRaises(ValueError):
                parameter.decode(bytearray(parameter.length))
        coolant = next(p for p in PARAMETERS if p.pid == 110)
        self.assertEqual(coolant.decode(b"\x00"), -17.777778)

    def test_unknown_pids_do_not_acquire_j1939_meanings(self):
        for pid in (1, 15, 174, 1023):
            data = b"\x01\x00" if pid == 174 else b"\x01"
            result = decode_report(J1587Report(130, pid, data))
            self.assertFalse(result["value_decoded"])
            self.assertEqual(result["signals"], [])
        for report in (
            b"\x80", Frame(0, bytes(8)),
            J1587Report(127, 190, bytes(2)),
            J1587Report(256, 190, bytes(2)),
            J1587Report(True, 190, bytes(2)),
            J1587Report(128, True, bytes(2)),
            J1587Report(128, -1, bytes(2)),
            J1587Report(128, 1024, bytes(2)),
            J1587Report(128, 190, bytearray(2)),
            J1587Report(128, 190, bytes(256)),
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                decode_report(report)

    def test_crankcase_pressure_is_signed_but_all_ones_stays_unavailable(self):
        parameter = next(p for p in PARAMETERS if p.pid == 101)
        self.assertTrue(parameter.signed)
        self.assertEqual(parameter.decode(b"\x80"), -110.316117)
        self.assertEqual(parameter.decode(b"\xfe"), -1.723689)
        self.assertIsNone(parameter.decode(b"\xff"))
        exported = next(
            p for p in export_catalog()["j1587_measurements"]
            if p["pid"] == 101
        )
        self.assertTrue(exported["signed"])

    def test_status_encodings_have_no_numeric_units_or_guessed_gears(self):
        for pid, data, value in (
            (40, b"\x01", "On"), (40, b"\x02", "Off"),
            (70, b"\x00", "Off"), (70, b"\x81", "On"),
            (85, b"\x81", "Active"), (85, b"\x00", "Inactive"),
            (162, b" N", "N"), (163, b" 6", "6"),
        ):
            result = decode_report(J1587Report(130, pid, data))
            self.assertTrue(result["value_decoded"])
            signal, = result["signals"]
            self.assertEqual(signal["value"], value)
            self.assertNotIn("unit", signal)
            if pid == 85:
                self.assertEqual(len(signal["switches"]), 8)
                self.assertEqual(
                    signal["switches"]["active"], value == "Active",
                )
        for parameter in STATUS_PARAMETERS:
            signal, = decode_report(J1587Report(
                128, parameter.pid, b"\xff" * parameter.length,
            ))["signals"]
            self.assertIsNone(signal["value"])
            for data in (bytes(parameter.length + 1), bytearray(1)):
                with self.assertRaises(ValueError):
                    parameter.decode(data)
        for data, status in (
            (b"\x00\x01", "unsupported_encoding"), (b"  ", "unavailable"),
        ):
            result = decode_report(J1587Report(130, 163, data))
            self.assertFalse(result["value_decoded"])
            self.assertEqual(result["signals"][0]["decode_status"], status)
        self.assertIn(174, READABLE_PIDS)
        self.assertTrue({195, 196, 192, 254}.isdisjoint(READABLE_PIDS))
        self.assertEqual(len(READABLE_PIDS), len(set(READABLE_PIDS)))


class J1708DatagramTests(unittest.TestCase):
    def test_checksum_and_multiple_parameters(self):
        message = parse_j1708_message(
            datagram(128, 190, 0xA0, 0x0F, 110, 212, 245, 4, 10, 0, 0, 0)
        )
        self.assertEqual(message.mid, 128)
        self.assertEqual([r.pid for r in message.reports], [190, 110, 245])
        self.assertEqual(message.reports[2].data, b"\x0a\x00\x00\x00")
        self.assertEqual(decode_report(message.reports[0])["signals"][0][
            "value"], 1000)

    def test_page_selector_applies_to_entire_datagram(self):
        message = parse_j1708_message(datagram(128, 255, 1, 10, 2, 11))
        self.assertEqual([r.pid for r in message.reports], [257, 258])
        message = parse_j1708_message(
            datagram(128, 255, 255, 255, 1, 10)
        )
        self.assertEqual(message.reports[0].pid, 769)
        self.assertFalse(decode_report(
            message.reports[0])["value_decoded"])

    def test_non_j1587_mid_stays_opaque(self):
        message = parse_j1708_message(datagram(10, 255, 0))
        self.assertEqual(message.reports, ())
        self.assertEqual(message.data, b"\xff\x00")
        parse_j1708_message(datagram(0))

    def test_rejects_malformed_datagrams_without_partial_return(self):
        for data in (
            b"", b"\x80", bytes(22), bytearray(datagram(128, 110, 100)),
            bytes.fromhex("80 be a0 0f 00"),
            datagram(128), datagram(128, 190, 1),
            datagram(128, 110), datagram(128, 245),
            datagram(128, 245, 4, 1),
            datagram(128, 255), datagram(128, 255, 255, 255, 255, 1, 1),
            datagram(128, 110, 100, 255, 1, 1),
            datagram(128, 254, 1), datagram(128, 110, 100, 190, 1),
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_j1708_message(data)


class DiagnosticTests(unittest.TestCase):
    def test_standard_expanded_pid_sid_and_occurrence_flags(self):
        result = decode_faults(
            # PID 91 FMI 3 active; SID 1 FMI 0 inactive count=7;
            # expanded PID 300 FMI 4 active count=0.
            bytes((91, 0x23, 1, 0xF0, 7, 44, 0x84, 0)), mid=128,
        )
        self.assertEqual(result["fault_count"], 3)
        self.assertEqual(result["active_fault_count"], 2)
        self.assertEqual(result["inactive_fault_count"], 1)
        a, b, c = result["faults"]
        self.assertEqual((a["namespace"], a["code"], a["fmi"]),
                         ("pid", 91, 3))
        self.assertIsNone(a["occurrence_count"])
        self.assertEqual((b["namespace"], b["code"], b["active"]),
                         ("sid", 1, False))
        self.assertEqual(b["occurrence_count"], 7)
        self.assertFalse(b["known"])
        self.assertEqual(c["code"], 300)
        self.assertTrue(c["expanded"])
        self.assertEqual(c["occurrence_count"], 0)
        self.assertIsNone(a["unit"])
        self.assertEqual(a["manufacturer_matches"], [])

    def test_profiles_and_empty_reports_do_not_imply_global_health(self):
        result = decode_report(
            J1587Report(128, 194, bytes((91, 0x23))),
            profile="detroit_ddec_iii_iv",
        )
        fault, = result["diagnostics"]["faults"]
        self.assertEqual(fault["manufacturer_matches"][0]["code"], "21")
        result = decode_faults(bytes((1, 0x10)), mid=130)
        self.assertEqual(result["faults"][0]["code"], 257)
        self.assertFalse(result["faults"][0]["known"])
        result = decode_faults(b"", mid=128)
        self.assertEqual(result["summary"], "No faults in this report")
        self.assertEqual(result["faults"], [])
        self.assertEqual(result["fault_count"], 0)

    def test_truncated_diagnostic_entries_raise(self):
        for data in (b"\x01", b"\x01\xa0", b"\x5b\x23\x01"):
            with self.assertRaises(ValueError):
                decode_faults(data, mid=128)
        with self.assertRaises(ValueError):
            decode_faults(b"", mid=128, profile="unknown")
        result = decode_faults(bytes((91, 0x2F)), mid=128)
        self.assertEqual(result["faults"][0]["failure_mode"],
                         "Reserved failure mode")


class ReplayTests(unittest.TestCase):
    def test_vendor_legacy_extended_and_raw_datagrams_agree(self):
        for body, extended in (
            (bytes.fromhex("9a 80 00 be 02 a0 0f"), False),
            (bytes.fromhex("9a 80 be 02 a0 0f"), True),
        ):
            record, = analyze_capture(
                StringIO(packet(body).hex()), padded_notifications=False,
                j1587_extended=extended,
            )
            self.assertTrue(record["value_decoded"])
            self.assertEqual(record["signals"][0]["value"], 1000)
        record, = analyze_j1708(StringIO(
            datagram(128, 190, 0xA0, 0x0F).hex()
        ))
        self.assertEqual(record["parameters"][0]["signals"][0]["value"], 1000)
        record, = analyze_j1708(StringIO(datagram(
            128, 194, 2, 91, 0x23
        ).hex()))
        self.assertEqual(record["parameters"][0]["diagnostics"][
            "active_fault_count"], 1)
        record, = analyze_j1708(StringIO(datagram(10, 0).hex()))
        self.assertEqual(record["protocol"], "j1708")
        self.assertEqual(record["parameters"], [])

    def test_line_errors_and_cli(self):
        for text in ("zz", "00", "0" * 129,
                     datagram(128, 190, 1).hex()):
            with self.assertRaisesRegex(ProtocolError, "Line 2:"):
                list(analyze_j1708(StringIO("\n" + text)))
        body = bytes.fromhex("9a 80 00 be 01 00")
        with self.assertRaisesRegex(ProtocolError, "Line 1:"):
            list(analyze_capture(
                StringIO(packet(body).hex()), padded_notifications=False,
                j1587_extended=False,
            ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "j1708.hex"
            path.write_text(datagram(128, 110, 212).hex(), encoding="ascii")
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([
                    str(path), "--transport", "j1708",
                ]), 0)
            self.assertEqual(json.loads(output.getvalue())["protocol"],
                             "j1587")
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main([str(path), "--transport", "j1708",
                      "--j1587-format", "extended"])


class PublishingTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_engine_identity_fault_catalog_and_stable_ownership(
        self,
    ):
        for profile in ("generic", "detroit_series_60_ddec_iv"):
            self.publish.reset_mock()
            bridge = MqttBridge(
                "coach", self.publish, engine_profile=profile,
                known_j1587=[[128, 168]],
            )
            await bridge.async_rediscover()
            await bridge.async_process_j1587(
                J1587Report(128, 194, bytes.fromhex("a8 21 fa 3c")),
            )
            await bridge.async_process_j1587(
                J1587Report(130, 194, bytes.fromhex("a8 21")),
            )
            configs = [
                json.loads(payload) for topic, payload, _ in self.messages()
                if topic.endswith("/config") and payload
            ]
            self.assertTrue(any(
                c["unique_id"] == "bluefire_coach_j1587_128_168"
                for c in configs
            ))
            states = {
                topic: json.loads(payload)
                for topic, payload, _ in self.messages()
                if "/faults/" in topic
            }
            engine = states["vehicle/coach/j1587/128/faults/194"]
            transmission = states["vehicle/coach/j1587/130/faults/194"]
            self.assertEqual(
                transmission["faults"][0]["manufacturer_matches"], [],
            )
            self.assertIsNone(transmission["faults"][0]["profile"])
            self.assertEqual(transmission["source_name"], "Transmission")
            if profile == "generic":
                self.assertEqual(engine["source_name"], "Engine")
                self.assertEqual(engine["faults"][0]["manufacturer_matches"],
                                 [])
            else:
                self.assertIn("DDEC IV", engine["source_name"])
                self.assertEqual(
                    engine["source_name_basis"],
                    "configured_official_equipment_labels",
                )
                self.assertEqual(
                    [f["manufacturer_matches"][0]["code"]
                     for f in engine["faults"]], ["46", "56"],
                )
                self.assertEqual(
                    bridge.diagnostics()["j1587"]["engine_profile"], profile,
                )
        with self.assertRaisesRegex(ValueError, "engine profile"):
            MqttBridge("coach", self.publish, engine_profile="guess")

    async def test_status_discovery_restores_and_removes_with_existing_ledger(
        self,
    ):
        for parameter in STATUS_PARAMETERS:
            data = b" N" if parameter.kind == "gear" else b"\x81"
            await self.bridge.async_process_j1587(
                J1587Report(130, parameter.pid, data),
            )
        configs = [
            json.loads(payload) for topic, payload, _ in self.messages()
            if topic.endswith("/config")
        ]
        for config in configs:
            self.assertNotIn("unit_of_measurement", config)
            self.assertNotIn("state_class", config)
        known = self.save.await_args.args[0]
        self.assertEqual(known, [[130, p.pid] for p in STATUS_PARAMETERS])
        restored = MqttBridge(
            "coach", self.publish, known_j1587=known, j1708_polling=True,
        )
        self.publish.reset_mock()
        await restored.async_rediscover()
        self.assertFalse(any(
            "/pid/" in topic for topic, _, _ in self.messages()
        ))
        restored_configs = [
            json.loads(payload) for topic, payload, _ in self.messages()
            if topic.startswith("homeassistant/sensor/")
        ]
        self.assertEqual(len(restored_configs), 5)
        self.assertTrue(all(c["expire_after"] == 60 for c in restored_configs))
        self.publish.reset_mock()
        await restored.async_remove_discovery()
        self.assertEqual(sum(
            payload == "" and topic.startswith("homeassistant/sensor/")
            for topic, payload, _ in self.messages()
        ), 5)

    async def test_identification_mid_isolation_and_removal(self):
        for mid, pid, data in (
            (128, 243, b"EXAMPLE ENGINE*MODEL*SERIAL*"),
            (130, 243, b"EXAMPLE TRANSMISSION*MODEL*SERIAL*"),
            (128, 234, b"EXAMPLE ECU SOFTWARE"),
            (128, 237, b"EXAMPLE VIN"),
            (175, 243, b"\x01\xff"),
        ):
            await self.bridge.async_process_j1587(J1587Report(mid, pid, data))
        messages = self.messages()
        for mid, pid in ((128, 243), (130, 243), (128, 234), (128, 237),
                         (175, 243)):
            config = json.loads(next(
                payload for topic, payload, _ in messages
                if topic == "homeassistant/sensor/"
                f"bluefire_coach_j1587_{mid}_{pid}/config"
            ))
            self.assertEqual(config["entity_category"], "diagnostic")
            self.assertNotIn("expire_after", config)
            self.assertNotIn("unit_of_measurement", config)
            self.assertNotIn("state_class", config)
            topic = f"vehicle/coach/j1587/{mid}/pid/{pid}"
            self.assertEqual(config["state_topic"], topic)
            self.assertEqual(config["json_attributes_topic"], topic)
            _, payload, retain = next(
                item for item in messages if item[0] == topic
            )
            self.assertFalse(retain)
            self.assertEqual(json.loads(payload)["mid"], mid)
        snapshot = self.bridge.diagnostics()["j1587"][
            "controller_identification"
        ]
        self.assertEqual(snapshot["128"]["243"]["value"],
                         "EXAMPLE ENGINE*MODEL*SERIAL*")
        self.assertEqual(snapshot["130"]["243"]["value"],
                         "EXAMPLE TRANSMISSION*MODEL*SERIAL*")
        self.assertEqual(snapshot["175"]["243"]["decode_status"],
                         "unsupported_encoding")
        known = self.save.await_args.args[0]
        self.assertEqual(known, [
            [128, 234], [128, 237], [128, 243], [130, 243], [175, 243],
        ])
        restored = MqttBridge("coach", self.publish, known_j1587=known)
        self.publish.reset_mock()
        await restored.async_rediscover()
        self.assertFalse(any(
            "/pid/" in topic for topic, _, _ in self.messages()
        ))
        self.publish.reset_mock()
        await restored.async_remove_discovery()
        self.assertEqual(sum(
            payload == "" and topic.endswith("/config") and retain
            for topic, payload, retain in self.messages()
        ), 7)
        await self.bridge.async_disconnected()
        self.assertEqual(
            self.bridge.diagnostics()["j1587"]["controller_identification"], {}
        )
        self.assertTrue(snapshot["128"]["243"]["value"])

    async def test_polling_extends_only_selected_reading_expiry(self):
        bridge = MqttBridge(
            "coach", self.publish, clock=self.clock, j1708_polling=True,
        )
        for pid, data in (
            (96, b"\x64"), (194, b""), (190, bytes(2)),
            (245, bytes(4)), (247, bytes(4)), (250, bytes(4)),
        ):
            await bridge.async_process_j1587(J1587Report(128, pid, data))
        await bridge.async_process_frame(Frame(
            (6 << 26) | (65276 << 8), bytes(8)
        ))
        configs = {
            topic: json.loads(payload)
            for topic, payload, _ in self.messages()
            if topic.endswith("/config")
        }
        for pid, expiry in (
            (96, 180), (194, 180), (245, 180), (247, 180), (250, 180),
            (190, 60),
        ):
            self.assertEqual(
                configs["homeassistant/sensor/"
                        f"bluefire_coach_j1587_128_{pid}/config"]
                ["expire_after"],
                expiry,
            )
        self.assertEqual(
            configs["homeassistant/sensor/bluefire_coach_0_96/config"]
            ["expire_after"],
            60,
        )
        self.clock.return_value = 160
        await bridge.async_check_stale()
        self.assertTrue(bridge.j1587._online)
        self.assertFalse(bridge._online)
        self.clock.return_value = 279
        await bridge.async_check_stale()
        self.assertTrue(bridge.j1587._online)
        self.clock.return_value = 280
        await bridge.async_check_stale()
        self.assertFalse(bridge.j1587._online)
        await bridge.async_process_j1587(J1587Report(128, 96, b"\x64"))
        self.assertTrue(bridge.j1587._online)
        await bridge.async_disconnected()
        self.assertFalse(bridge.j1587._online)

    async def asyncSetUp(self):
        self.publish, self.save = AsyncMock(), AsyncMock()
        self.clock = Mock(return_value=100)
        self.bridge = MqttBridge(
            "coach", self.publish, save_j1587=self.save, clock=self.clock
        )

    def messages(self):
        return [call.args for call in self.publish.await_args_list]

    async def test_j1587_and_j1939_namespace_identity_and_unit_isolation(self):
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes.fromhex("a0 0f"))
        )
        await self.bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes.fromhex(
                "ff ff 7d 40 1f ff ff ff"
            ))
        )
        messages = {
            topic: json.loads(payload) for topic, payload, _ in self.messages()
            if payload not in ("online", "offline")
        }
        j1587 = messages["vehicle/coach/j1587/128/pid/190"]
        j1939 = messages["vehicle/coach/j1939/0/spn/190"]
        self.assertEqual(j1587["value"], j1939["value"])
        self.assertEqual(j1587["unit"], "rpm")
        self.assertEqual(j1587["datalink"], "j1708")
        self.assertNotIn("spn", j1587)
        self.assertNotIn("pgn", j1587)
        self.assertNotIn("can_id", j1587)
        self.assertNotIn("source_address", j1587)
        config = messages[
            "homeassistant/sensor/bluefire_coach_j1587_128_190/config"
        ]
        self.assertEqual(config["name"], "Engine: Speed")
        self.assertEqual(config["suggested_display_precision"], 2)
        self.assertEqual(config["unit_of_measurement"], "rpm")
        self.assertEqual(config["expire_after"], 60)
        self.assertEqual(config["availability_topic"],
                         "vehicle/coach/j1587/availability")
        self.assertEqual(config["device"],
                         messages["homeassistant/sensor/"
                                  "bluefire_coach_0_190/config"]["device"])
        self.save.assert_awaited_once_with([[128, 190]])
        raw = messages["vehicle/coach/j1587/128/report"]
        self.assertEqual(raw["data"], "a00f")
        self.assertEqual(raw["pid"], 190)

    async def test_every_parameter_and_multiple_mids(self):
        for mid in (128, 130):
            for parameter in PARAMETERS:
                await self.bridge.async_process_j1587(J1587Report(
                    mid, parameter.pid, bytes(parameter.length)
                ))
        messages = {
            t: json.loads(p) for t, p, _ in self.messages()
            if p not in ("online", "offline")
        }
        for mid in (128, 130):
            for parameter in PARAMETERS:
                state = messages[
                    f"vehicle/coach/j1587/{mid}/pid/{parameter.pid}"
                ]
                self.assertEqual(state["unit"], parameter.unit)
                self.assertEqual(state["value"],
                                 round(parameter.offset, 6))
                config = messages[
                    "homeassistant/sensor/"
                    f"bluefire_coach_j1587_{mid}_{parameter.pid}/config"
                ]
                self.assertEqual(config["state_class"],
                                 parameter.state_class)
                self.assertEqual(config.get("device_class"),
                                 parameter.device_class)
                self.assertEqual(
                    config["suggested_display_precision"],
                    1 if parameter.unit in ("%", "°C") else 2,
                )
                self.assertIn("mid", config["json_attributes_template"])
        self.assertEqual(
            len(self.save.await_args.args[0]), 2 * len(PARAMETERS)
        )

    async def test_voltage_and_fuel_flow_keep_fractional_values(self):
        fixtures = (
            (128, 168, 268, 13.4, "Engine: Supply voltage"),
            (136, 168, 265, 13.25, "Brakes: Supply voltage"),
            (128, 183, 80, 4.731765, "Engine: Fuel rate"),
        )
        for mid, pid, raw, value, name in fixtures:
            await self.bridge.async_process_j1587(
                J1587Report(mid, pid, raw.to_bytes(2, "little"))
            )
        messages = {
            t: (json.loads(p), retained) for t, p, retained in self.messages()
            if p not in ("online", "offline")
        }
        for mid, pid, raw, value, name in fixtures:
            with self.subTest(mid=mid, pid=pid):
                config, retained = messages[
                    "homeassistant/sensor/"
                    f"bluefire_coach_j1587_{mid}_{pid}/config"
                ]
                self.assertTrue(retained)
                self.assertEqual(config["name"], name)
                self.assertEqual(config["suggested_display_precision"], 2)
                self.assertEqual(
                    config["unique_id"],
                    f"bluefire_coach_j1587_{mid}_{pid}",
                )
                state, retained = messages[config["state_topic"]]
                self.assertFalse(retained)
                self.assertEqual(state["value"], value)
                self.assertEqual(state["mid"], mid)
                self.assertEqual(state["pid"], pid)

    async def test_restored_names_distinguish_unknown_controllers(self):
        restored = MqttBridge(
            "coach", self.publish,
            known_j1587=[[128, 110], [191, 110], [253, 110]],
        )
        await restored.async_rediscover()
        configs = {
            json.loads(p)["name"]: json.loads(p)
            for topic, p, _ in self.messages() if "/sensor/" in topic
        }
        self.assertEqual(set(configs), {
            "Engine: Coolant temperature",
            "Controller 191: Coolant temperature",
            "Controller 253: Coolant temperature",
        })
        for config in configs.values():
            self.assertEqual(config["suggested_display_precision"], 1)
            self.assertIn("mid", config["json_attributes_template"])
            self.assertIn("pid", config["json_attributes_template"])
        self.assertTrue(all(t.endswith("/config") and retained
                            for t, _, retained in self.messages()))

    async def test_fault_discovery_replace_clear_and_unavailable_values(self):
        for data in (bytes((91, 0x23)), b""):
            await self.bridge.async_process_j1587(J1587Report(128, 194, data))
        for data in (bytes.fromhex("a0 0f"), b"\xff\xff"):
            await self.bridge.async_process_j1587(J1587Report(128, 190, data))
        faults = [
            json.loads(p) for t, p, _ in self.messages()
            if t.endswith("/faults/194")
        ]
        self.assertEqual([f["fault_count"] for f in faults], [1, 0])
        values = [
            json.loads(p)["value"] for t, p, _ in self.messages()
            if t.endswith("/pid/190")
        ]
        self.assertEqual(values, [1000, None])
        configs = [
            json.loads(p) for t, p, _ in self.messages()
            if t.endswith("_194/config")
        ]
        config, = configs
        self.assertNotIn("unit_of_measurement", config)
        self.assertNotIn("suggested_display_precision", config)
        self.assertEqual(config["entity_category"], "diagnostic")

    async def test_separate_protocol_freshness_and_recovery(self):
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes(2))
        )
        self.clock.return_value = 159
        await self.bridge.async_check_stale()
        await self.bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes(8))
        )
        self.publish.reset_mock()
        self.clock.return_value = 160
        await self.bridge.async_check_stale()
        self.assertEqual(self.messages(), [
            ("vehicle/coach/j1587/availability", "offline", True),
        ])
        self.assertTrue(self.bridge._online)
        await self.bridge.async_check_stale()
        self.assertEqual(len(self.messages()), 1)
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes(2))
        )
        self.assertEqual(self.messages()[-1],
                         ("vehicle/coach/j1587/availability", "online", True))
        self.publish.reset_mock()
        await self.bridge.async_disconnected()
        self.assertEqual({t for t, _, _ in self.messages()}, {
            "vehicle/coach/j1939/availability",
            "vehicle/coach/j1587/availability",
        })
        self.assertFalse(self.bridge.j1587._online)

    async def test_restoration_and_cleanup_without_replaying_values(self):
        await self.bridge.async_process_j1587(
            J1587Report(130, 190, bytes(2))
        )
        ids = self.save.await_args.args[0]
        self.publish.reset_mock()
        restored = MqttBridge(
            "coach", self.publish, known_j1587=ids,
            save_j1587=self.save,
        )
        await restored.async_rediscover()
        self.assertEqual(len(self.messages()), 3)
        self.assertTrue(all(
            topic.endswith("/config") and retain
            for topic, _, retain in self.messages()
        ))
        self.publish.reset_mock()
        await restored.async_remove_discovery()
        self.publish.assert_any_await(
            "homeassistant/sensor/bluefire_coach_j1587_130_190/config",
            "", True,
        )
        self.save.assert_awaited_with([])

    async def test_unknown_parameters_raw_only_and_invalid_inputs_atomic(self):
        await self.bridge.async_process_j1587(
            J1587Report(130, 174, b"\x01\x00")
        )
        self.assertEqual(len(self.messages()), 2)
        self.assertTrue(self.messages()[0][0].endswith("/report"))
        self.save.assert_not_awaited()
        self.publish.reset_mock()
        for value in (
            J1587Report(0, 190, bytes(2)), J1587Report(128, 190, bytes(1)),
            J1587Report(128, 194, b"\x01"),
        ):
            with self.assertRaises(ValueError):
                await self.bridge.async_process_j1587(value)
        with self.assertRaises(ValueError):
            await self.bridge.j1587.async_process_frame(Frame(0, bytes(8)))
        with self.assertRaises(ValueError):
            await self.bridge.async_process_j1708(datagram(10, 0))
        with self.assertRaises(ValueError):
            await self.bridge.async_process_j1708(
                datagram(128, 110, 212, 194, 1, 1)
            )
        self.publish.assert_not_awaited()
        await self.bridge.async_process_j1708(
            datagram(128, 110, 212, 190, 0xA0, 0x0F)
        )
        self.assertEqual(sum(t.endswith("/report")
                             for t, _, _ in self.messages()), 2)

    async def test_persistence_and_broker_errors_are_retryable(self):
        self.save.side_effect = OSError("disk unavailable")
        with self.assertRaises(OSError):
            await self.bridge.async_process_j1587(
                J1587Report(128, 190, bytes(2))
            )
        self.assertFalse(any(t.endswith("/config")
                             for t, _, _ in self.messages()))
        self.assertFalse(self.bridge.j1587._online)
        self.save.side_effect = None
        self.publish.side_effect = [None, RuntimeError("broker unavailable")]
        with self.assertRaises(RuntimeError):
            await self.bridge.async_process_j1587(
                J1587Report(128, 190, bytes(2))
            )
        self.assertEqual(self.bridge.j1587.discovery, {})
        self.publish.side_effect = None
        await asyncio.gather(*(
            self.bridge.async_process_j1587(J1587Report(128, 190, bytes(2)))
            for _ in range(2)
        ))
        self.assertEqual(len(self.bridge.j1587.discovery), 1)

    def test_untrusted_ownership_only_accepts_known_mid_pid_pairs(self):
        self.assertEqual(validated_j1587_ids([
            [128, 190], [130, 194], [255, 190],
            [0, 190], [128, 513], [128, -65226],
            [True, 190], [128, True], [256, 190], "bad", [],
        ]), [[128, 190], [130, 194], [255, 190]])
        self.assertEqual(validated_j1587_ids({}), [])
