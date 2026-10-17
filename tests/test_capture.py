"""Offline analysis of raw notification captures and health counters."""

from datetime import datetime, timedelta, timezone
import unittest

from custom_components.bluefire.capture import (
    analyze_notifications,
    record_capture,
    serialize_notifications,
)
from custom_components.bluefire.health import ERROR_MESSAGES, Health

from test_boundaries import packet


def note(t, data, characteristic="j1939", handle=12):
    return {
        "t": t, "characteristic": characteristic, "handle": handle,
        "data": data,
    }


class CaptureAnalysisTests(unittest.TestCase):
    def test_empty_capture(self):
        analysis = analyze_notifications([])
        self.assertEqual(analysis["timing"]["notifications"], 0)
        self.assertIsNone(analysis["timing"]["rate_per_s"])
        self.assertEqual(analysis["selected_framing"], "stream")
        self.assertEqual(analysis["characteristics"], {})

    def test_reports_are_tallied_per_type(self):
        notifications = [
            note(0.0, packet(bytes([151, 0, 0xF0, 0x04, 3, 0, 1, 0]))),
            note(0.5, packet(bytes([151, 1, 0x30, 0x39, 6, 0, 1, 0xAA]))),
            note(1.0, packet(bytes([154, 128, 0, 84, 1, 0x20]))),
            note(1.5, packet(bytes([154, 128, 84, 1, 0x20]))),
            note(2.0, packet(bytes([154, 128]))),
            note(2.5, packet(bytes([174, 0, 1, 1, 0, 12, 2, 1, 2]))),
            note(3.0, packet(bytes([0xFF]))),
            note(3.5, packet(bytes([7]))),
        ]
        analysis = analyze_notifications(notifications)
        stream = analysis["characteristics"]["j1939#12"]["framing"]["stream"]
        self.assertEqual(stream["packets"], 7)
        self.assertEqual(stream["parse_errors"], 1)
        self.assertEqual(stream["decode_success_rate"], 87.5)
        self.assertEqual(stream["pgn_reports"], 2)
        self.assertEqual(stream["unrecognized_pgns"], 1)
        self.assertEqual(stream["pgns"]["61444"]["sources"], [0])
        self.assertTrue(stream["pgns"]["61444"]["known"])
        self.assertFalse(stream["pgns"]["12345"]["known"])
        self.assertEqual(stream["j1587_mid_pid"], {"128:84": 2})
        self.assertEqual(
            stream["j1587_formats_accepted"], {"legacy": 1, "extended": 1}
        )
        self.assertEqual(stream["obd_source_mode_pid"], {"1:1:12": 1})
        self.assertEqual(stream["heartbeats"], 1)
        self.assertEqual(stream["unknown_commands"], 1)
        self.assertEqual(stream["commands"]["255"]["name"], "Heartbeat")
        self.assertEqual(stream["samples"][0]["kind"], "PgnReport")
        self.assertEqual(stream["samples"][0]["data"], "00")
        timing = analysis["timing"]
        self.assertEqual(timing["mean_interval_s"], 0.5)
        self.assertEqual(timing["max_gap_s"], 0.5)
        self.assertEqual(timing["rate_per_s"], 2.29)

    def test_padded_notifications_are_selected_when_they_fit(self):
        heartbeat = packet(b"\xff")
        analysis = analyze_notifications([
            note(0.0, heartbeat + bytes(15)),
            note(0.1, heartbeat + bytes(15)),
            note(0.2, bytes(20), "j1708", 15),
        ])
        self.assertEqual(analysis["selected_framing"], "padded")
        self.assertEqual(analysis["totals"]["padded"]["packets"], 2)
        self.assertGreater(analysis["totals"]["stream"]["framing_errors"], 0)
        timing = analysis["characteristics"]["j1708#15"]["timing"]
        self.assertEqual(timing["zero_filled"], 1)
        self.assertEqual(timing["length_histogram"], {"20": 1})

    def test_serialization_and_health_recording(self):
        health = Health()
        notifications = [
            note(0.0, packet(b"\xff")), note(0.1, b"\x00\x01\x00"),
        ]
        analysis = analyze_notifications(notifications)
        self.assertEqual(serialize_notifications(notifications)[1], {
            "t": 0.1, "characteristic": "j1939", "handle": 12, "length": 3,
            "hex": "000100",
        })
        calls = []
        health.add_listener(lambda: calls.append(True))
        record_capture(health, analysis)
        self.assertEqual(len(calls), 1)
        self.assertEqual(health.counters["notifications"], 2)
        self.assertEqual(health.counters["bytes"], 8)
        self.assertEqual(health.counters["packets"], 1)
        self.assertEqual(health.counters["heartbeats"], 1)
        self.assertEqual(health.counters["framing_errors"], 1)
        self.assertEqual(health.counters["captures"], 1)
        self.assertIsNotNone(health.last_data)
        self.assertEqual(health.decode_success_rate, 50.0)
        self.assertEqual(
            health.last_capture_summary["selected_framing"], "stream"
        )
        empty = Health()
        record_capture(empty, analyze_notifications([]), notify=False)
        self.assertIsNone(empty.last_data)
        self.assertEqual(empty.counters["captures"], 1)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.health = Health(clock=lambda: self.now)

    def test_empty_state(self):
        result = self.health.as_dict()
        self.assertIsNone(result["decode_success_rate"])
        self.assertIsNone(result["rssi_statistics"])
        self.assertIsNone(result["last_data"])
        self.assertEqual(result["started"], "2026-01-01T00:00:00+00:00")

    def test_advertisements_notify_only_on_presence_change(self):
        calls = []
        remove = self.health.add_listener(lambda: calls.append(True))
        self.health.advertisement(-80, "hci0")
        self.now += timedelta(seconds=1)
        self.health.advertisement(-60, "proxy")
        self.health.advertisement(None, "proxy")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.health.rssi_statistics(), {
            "samples": 2, "min": -80, "max": -60, "mean": -70.0,
            "spread": 20,
        })
        self.health.unavailable()
        self.assertEqual(len(calls), 2)
        remove()
        self.health.advertisement(-70, "hci0")
        self.assertEqual(len(calls), 2)
        result = self.health.as_dict()
        self.assertEqual(result["counters"]["advertisements"], 4)
        self.assertEqual(result["last_advertisement"],
                         "2026-01-01T00:00:01+00:00")

    def test_error_messages_are_bounded(self):
        for index in range(ERROR_MESSAGES + 5):
            self.health.error("mqtt_errors", f"topic/{index}", notify=False)
        self.assertEqual(self.health.counters["mqtt_errors"],
                         ERROR_MESSAGES + 5)
        self.assertEqual(
            self.health.error_messages["mqtt_errors: (other messages)"], 5
        )
        self.assertEqual(len(self.health.recent_errors), 50)
        self.assertEqual(
            self.health.last_error, f"mqtt_errors: topic/{ERROR_MESSAGES + 4}"
        )
