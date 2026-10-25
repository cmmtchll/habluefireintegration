"""Wire vectors and guarded, unsecured startup state transitions."""

import asyncio
import unittest
from unittest.mock import patch

from custom_components.bluefire.j1587 import ENTITIES
from custom_components.bluefire.protocol import AdapterMessage
from custom_components.bluefire.startup import (
    CLIENT_COMPATIBILITY,
    J1708Startup,
    StartupError,
    client_packet,
    pid_subscription,
)


def version_response(major=3, minor=23, patch_version=0):
    return bytes((major, minor, 4, 1, patch_version)) + bytes(16)


class ClientPacketTests(unittest.TestCase):
    def test_subscription_rejects_unknown_and_non_integer_pids(self):
        for pid in (True, "96", 195, -1):
            with self.subTest(pid=pid), self.assertRaises(StartupError):
                pid_subscription(pid)

    def test_direction_specific_vectors_and_att_limit(self):
        self.assertEqual(client_packet(b"\x00"), bytes.fromhex("000100fe"))
        self.assertEqual(
            client_packet(b"\x09\x0c\x05"), bytes.fromhex("0003090c05e2")
        )
        self.assertEqual(
            client_packet(b"\x99\x01"), bytes.fromhex("0002990163")
        )
        self.assertEqual(len(client_packet(bytes(17))), 20)
        # End-around carry, not a modulo-256 checksum.
        self.assertEqual(client_packet(b"\xff\xff")[-1], 253)

    def test_invalid_bodies_are_rejected(self):
        for body in (b"", bytes(18), bytearray(b"\x00"), None):
            with self.subTest(body=body), self.assertRaises(StartupError):
                client_packet(body)


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_shot_reads_are_allowlisted_and_restore_monitoring(self):
        startup = self.make_startup()
        with self.assertRaisesRegex(StartupError, "not ready"):
            await startup.async_read(96)
        await startup.run()
        for pid in (96, 194):
            await startup.async_read(pid)
            self.assertEqual(
                self.sent[-1],
                b"\x9b\x00" + pid.to_bytes(2, "big")
                + b"\x01\x01\x00\x00\x00",
            )
            await startup.async_read(pid, restore=True)
            self.assertEqual(
                self.sent[-1],
                b"\x9b\x00" + pid.to_bytes(2, "big")
                + b"\x00\x02\x03\xe8\x00",
            )
        for pid in (195, True, "96"):
            with self.assertRaisesRegex(StartupError, "Only fuel"):
                await startup.async_read(pid)
        self.assertTrue(startup.ready)

    def make_startup(
        self, *, name="BlueFire EZ", extended=True, overrides=None,
    ):
        self.sent = []
        self.responses = {
            0: version_response(),
            9: b"\x01",
            130: b"\x01",
            171: b"\x01",
            169: b"\x01",
            206: bytes(15 if "-" not in name else (
                33 if name.endswith("4.0.0") else 32
            )),
            7: b"\x01",
            8: b"",
        }
        self.responses.update(overrides or {})

        async def write(packet):
            self.assertLessEqual(len(packet), 20)
            self.assertEqual(
                int.from_bytes(packet[:2], "big"), len(packet) - 3
            )
            self.assertEqual(sum(packet) % 255, 0)
            body = packet[2:-1]
            self.sent.append(body)
            command = body[0]
            if command == 153:
                response = self.responses.get(153, body[1:])
            else:
                response = self.responses.get(command)
            if response is not None:
                self.startup.receive(AdapterMessage(command, response))

        self.startup = J1708Startup(write, name, extended)
        self.startup.receive(AdapterMessage(255, b""))
        return self.startup

    async def test_firmware_323_unsecured_startup_and_all_passive_pids(self):
        startup = self.make_startup()
        await startup.run()
        self.assertTrue(startup.ready)
        self.assertEqual(startup.firmware, (3, 23, 0))
        self.assertEqual(
            self.sent[:9],
            [
                b"\x00", b"\x96\x05\x00", b"\x09\x0c\x05",
                b"\x82\x00", b"\xab\x00", b"\xce", b"\x07",
                b"\x08", b"\x99\x00",
            ],
        )
        subscriptions = self.sent[9:-1]
        self.assertEqual(len(subscriptions), len(ENTITIES))
        for body, parameter in zip(subscriptions, ENTITIES):
            self.assertEqual(
                body,
                b"\x9b\x00" + parameter.pid.to_bytes(2, "big")
                + b"\x00\x02\x03\xe8\x00",
            )
        self.assertEqual(self.sent[-1], b"\x99\x01")
        self.assertEqual(startup.diagnostics(), {
            "stage": "ready", "profile": 3, "firmware": [3, 23, 0],
            "expected_command": None, "j1708_available": True,
            "subscriptions_sent": len(ENTITIES), "discarded_reports": 0,
            "error": None,
        })
        # No security writes, reset, bus settings, SendPID or fault clearing.
        self.assertFalse(
            {139, 144, 152, 168, 170, 200, 207, 209, 211, 215, 227}
            & {body[0] for body in self.sent}
        )

    async def test_firmware_four_profiles_are_separate(self):
        for version in ("4.0.0", "4.1.0", "4.2.3"):
            with self.subTest(version=version):
                startup = self.make_startup(
                    name=f"BlueFire EZ 4.1-{version}"
                )
                await startup.run()
                self.assertTrue(startup.ready)
                self.assertEqual(
                    self.sent[0], bytes((9, *CLIENT_COMPATIBILITY, 0))
                )
                self.assertEqual(self.sent[1], b"\xa9\x00\x00\x00")
                self.assertNotIn(b"\x00", self.sent)
                self.assertEqual(startup.profile, 4)

    async def test_legacy_format_requires_matching_firmware(self):
        startup = self.make_startup(
            extended=False, overrides={0: version_response(minor=18)}
        )
        await startup.run()
        self.assertTrue(startup.ready)

    async def test_initial_bus_status_does_not_gate_passive_report_setup(self):
        for name in ("BlueFire EZ", "BlueFire EZ 4.1-4.2.3"):
            with self.subTest(name=name):
                startup = self.make_startup(
                    name=name, overrides={7: b"\x00"}
                )
                with self.assertLogs(
                    "custom_components.bluefire.startup", level="WARNING"
                ) as logs:
                    await startup.run()
                self.assertTrue(startup.ready)
                self.assertFalse(startup.j1708_available)
                self.assertIsNone(startup.error)
                self.assertEqual(startup.subscriptions_sent, len(ENTITIES))
                self.assertIn(b"\x08", self.sent)
                self.assertEqual(self.sent[-1], b"\x99\x01")
                self.assertIn("waiting for telemetry", logs.output[0])

    async def test_rejections_and_malformed_responses_fail_closed(self):
        cases = (
            ({0: bytes(21)}, "Malformed firmware"),
            ({0: bytes(20)}, "Malformed firmware"),
            ({0: version_response(major=2)}, "Unsupported firmware"),
            ({0: version_response(minor=13)}, "Unsupported firmware"),
            ({0: version_response(minor=18)}, "format disagrees"),
            ({9: b"\x00"}, "compatibility rejected"),
            ({9: b""}, "Malformed compatibility"),
            ({130: b"\x00"}, "authentication_1 rejected"),
            ({171: b"\x00"}, "authentication_2 rejected"),
            ({171: b"\x01\x01"}, "Malformed authentication_2"),
            ({206: bytes(14)}, "Malformed firmware 3.x variables"),
            ({7: b"\x02"}, "Malformed J1708 availability"),
            ({8: b"\x00"}, "Unexpected application_connected"),
            ({153: b"\x02"}, "Unexpected stop_reports"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                startup = self.make_startup(overrides=overrides)
                with self.assertRaisesRegex(StartupError, message):
                    await startup.run()
                self.assertFalse(startup.ready)
                self.assertEqual(startup.stage, "failed")
                self.assertIsNotNone(startup.error)
                self.assertIsNone(startup.expected_command)
                self.assertNotIn(b"\x99\x01", self.sent)
                startup.disconnected()
                self.assertEqual(startup.stage, "failed")

    async def test_firmware_four_rejections(self):
        for version, size, index in (("4.0.0", 33, 13), ("4.2.3", 32, 11)):
            disabled = bytearray(size)
            disabled[index] = 1
            for overrides, error in (
                ({169: b"\x00"}, "authentication rejected"),
                ({206: bytes(size - 1)}, "Truncated"),
                ({206: bytes(disabled)}, "J1708 is disabled"),
            ):
                with self.subTest(version=version, error=error):
                    startup = self.make_startup(
                        name=f"BlueFire EZ 4.1-{version}",
                        overrides=overrides,
                    )
                    with self.assertRaisesRegex(StartupError, error):
                        await startup.run()
                    self.assertNotIn(b"\x99\x01", self.sent)

    async def test_heartbeat_and_response_timeouts(self):
        for heartbeat in (False, True):
            startup = self.make_startup(overrides={0: None})
            if not heartbeat:
                startup._heartbeat.clear()
            with patch(
                "custom_components.bluefire.startup.STEP_TIMEOUT", 0.01
            ):
                with self.assertRaisesRegex(
                    StartupError,
                    "Timed out during " + (
                        "version" if heartbeat else "waiting_for_heartbeat"
                    ),
                ):
                    await startup.run()
            self.assertIsNone(startup.expected_command)
            self.assertEqual(startup.stage, "failed")

    async def test_cancellation_during_response_wait_clears_future(self):
        startup = self.make_startup(overrides={0: None})
        task = asyncio.create_task(startup.run())
        await asyncio.sleep(0)
        self.assertEqual(startup.expected_command, 0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        startup.disconnected()
        self.assertEqual(startup.stage, "disconnected")
        self.assertIsNone(startup._response)

    async def test_unrelated_and_duplicate_controls_do_not_resolve(self):
        startup = self.make_startup(overrides={0: None})
        self.assertFalse(startup.receive(AdapterMessage(42, b"")))
        with self.assertRaisesRegex(StartupError, "Malformed heartbeat"):
            startup.receive(AdapterMessage(255, b"\x01"))
        with self.assertRaisesRegex(StartupError, "rejected"):
            startup.receive(AdapterMessage(155, b"\x00"))
        with self.assertRaisesRegex(StartupError, "authentication"):
            startup.receive(AdapterMessage(169, b"\x00"))
        task = asyncio.create_task(startup.run())
        await asyncio.sleep(0)
        startup.receive(AdapterMessage(9, b"\x01"))
        self.assertFalse(startup._response.done())
        response = AdapterMessage(0, version_response())
        startup.receive(response)
        startup.receive(response)
        await task
        self.assertTrue(startup.ready)
        self.assertTrue(startup.receive(AdapterMessage(255, b"")))
        self.assertEqual(len([b for b in self.sent if b == b"\x00"]), 1)

    async def test_start_reports_requires_its_own_acknowledgement(self):
        startup = self.make_startup()
        original = startup._write

        async def write(packet):
            if packet[2:-1] == b"\x99\x01":
                startup.receive(AdapterMessage(153, b"\x00"))
            else:
                await original(packet)

        startup._write = write
        with self.assertRaisesRegex(StartupError, "Unexpected start_reports"):
            await startup.run()
        self.assertFalse(startup.ready)
