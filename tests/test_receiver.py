"""Exercise the provisional BLE receiver without a radio or broker."""

import importlib
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.health import Health
from custom_components.bluefire.j1587 import ENTITIES
from custom_components.bluefire.telemetry import MqttBridge


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def run_poll_cycles(self, cycles, read, *, before_cycle=None):
        self.configure_read()
        clock = [0]
        sleeps = []

        async def sleep(delay):
            sleeps.append(delay)
            if len(sleeps) > cycles:
                raise asyncio.CancelledError
            clock[0] += delay
            if before_cycle is not None:
                before_cycle(len(sleeps))

        self.receiver.async_read = AsyncMock(
            side_effect=lambda pid: read(pid, clock)
        )
        with (
            patch.object(self.api, "monotonic", side_effect=lambda: clock[0]),
            patch.object(self.api.asyncio, "sleep", side_effect=sleep),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.receiver._async_poll()
        return sleeps

    async def test_polling_runs_each_minute_without_read_duration_drift(self):
        reads = []

        def read(pid, clock):
            reads.append((clock[0], pid))
            clock[0] += 5

        sleeps = await self.run_poll_cycles(3, read)
        self.assertEqual(reads, [
            (60, 96), (65, 194), (70, 245), (75, 247), (80, 250),
            (120, 96), (125, 194), (130, 245), (135, 247), (140, 250),
            (180, 96), (185, 194), (190, 245), (195, 247), (200, 250),
        ])
        self.assertEqual(sleeps, [60, 35, 35, 35])

    async def test_slow_poll_round_does_not_burst_to_catch_up(self):
        reads = []

        def read(pid, clock):
            reads.append((clock[0], pid))
            clock[0] += 20

        sleeps = await self.run_poll_cycles(2, read)
        self.assertEqual(sleeps, [60, 60, 60])
        self.assertEqual(reads[:5], [
            (60, 96), (80, 194), (100, 245), (120, 247), (140, 250),
        ])
        self.assertEqual(reads[5:], [
            (220, 96), (240, 194), (260, 245), (280, 247), (300, 250),
        ])

    async def test_poll_backoff_is_per_pid_capped_and_resets_on_success(self):
        reads = []

        def read(pid, clock):
            reads.append((clock[0], pid))
            if pid == 96 and clock[0] < 1800:
                raise self.home_assistant_error("No fuel report")

        with self.assertLogs(
            "custom_components.bluefire.receiver", level="WARNING",
        ) as logs:
            await self.run_poll_cycles(31, read)
        self.assertEqual(
            [time for time, pid in reads if pid == 96],
            [60, 180, 420, 900, 1800, 1860],
        )
        for successful_pid in (194, 245, 247, 250):
            self.assertEqual(
                [time for time, pid in reads if pid == successful_pid],
                list(range(60, 1861, 60)),
            )
        self.assertEqual(self.receiver.health.counters["connection_errors"], 4)
        self.assertIn("retrying in 900 seconds", logs.output[-1])

    async def test_polling_skips_busy_read_and_retries_next_minute(self):
        reads = []
        waiter = asyncio.get_running_loop().create_future()

        def before_cycle(cycle):
            self.receiver._read_waiter = waiter if cycle == 1 else None

        await self.run_poll_cycles(
            2, lambda pid, clock: reads.append((clock[0], pid)),
            before_cycle=before_cycle,
        )
        waiter.cancel()
        self.assertEqual(reads, [
            (120, 96), (120, 194), (120, 245), (120, 247), (120, 250),
        ])

    async def test_polling_stops_if_connection_is_not_ready(self):
        for state in ("closed", "paused", "missing", "not_ready", "reconnect"):
            with self.subTest(state=state):
                self.configure_read()
                self.receiver._closed = state == "closed"
                self.receiver._paused = state == "paused"
                if state == "missing":
                    self.receiver._startup = None
                elif state == "not_ready":
                    self.receiver._startup.ready = False
                if state == "reconnect":
                    self.receiver._reconnect_event.set()
                self.receiver.async_read = AsyncMock()
                with patch.object(self.api.asyncio, "sleep", new=AsyncMock()):
                    await self.receiver._async_poll()
                self.receiver.async_read.assert_not_awaited()

    async def test_poll_task_starts_after_startup_and_is_cancelled_per_session(
        self,
    ):
        self.configure_startup_session()
        self.bridge.async_process_j1587.side_effect = None
        poll_started = asyncio.Event()
        poll_stopped = asyncio.Event()

        async def poll():
            self.assertTrue(self.receiver._startup.ready)
            poll_started.set()
            try:
                await asyncio.Future()
            finally:
                poll_stopped.set()

        self.receiver._async_poll = AsyncMock(side_effect=poll)
        for _ in range(2):
            self.client.is_connected = True
            poll_started.clear()
            poll_stopped.clear()
            task = asyncio.create_task(self.receiver._async_receive_session())
            await asyncio.wait_for(poll_started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(poll_stopped.is_set())
        self.assertEqual(self.receiver._async_poll.await_count, 2)
        self.assertEqual(self.client.disconnect.await_count, 2)

    async def test_poll_task_failure_is_not_silently_lost(self):
        self.configure_startup_session()
        self.bridge.async_process_j1587.side_effect = None
        self.receiver._async_poll = AsyncMock(
            side_effect=RuntimeError("poll worker failed")
        )
        with self.assertRaisesRegex(RuntimeError, "poll worker failed"):
            await asyncio.wait_for(self.receiver._async_receive_session(), 1)
        self.client.disconnect.assert_awaited_once()

    async def test_keepalive_and_polling_serialize_ble_writes(self):
        self.configure_startup_session()
        self.bridge.async_process_j1587.side_effect = None
        original_write = self.client.write_gatt_char.side_effect
        probe_started = asyncio.Event()
        release_probe = asyncio.Event()
        read_started = asyncio.Event()
        read_completed = asyncio.Event()
        active_writes = 0
        max_active_writes = 0

        async def write(characteristic, packet, *, response):
            nonlocal active_writes, max_active_writes
            active_writes += 1
            max_active_writes = max(max_active_writes, active_writes)
            try:
                body = packet[2:-1]
                if body == b"\x07" and self.receiver._startup.ready:
                    probe_started.set()
                    await release_probe.wait()
                await original_write(characteristic, packet, response=response)
                if body == bytes.fromhex("9b 00 00 60 01 01 00 00 00"):
                    self.receiver._notification_received(
                        None, self.packet(bytes.fromhex("9a 80 60 01 64"))
                    )
            finally:
                active_writes -= 1

        async def poll():
            await probe_started.wait()
            read_started.set()
            result = await self.receiver.async_read(96)
            self.assertEqual(result["reports"][0]["signals"][0]["value"], 50)
            read_completed.set()
            await asyncio.Future()

        self.client.write_gatt_char.side_effect = write
        self.receiver._async_poll = AsyncMock(side_effect=poll)
        with (
            patch(
                "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
            ),
            patch.object(self.api, "READ_WINDOW_SECONDS", 0.2),
        ):
            task = asyncio.create_task(self.receiver.async_run())
            try:
                await asyncio.wait_for(read_started.wait(), 1)
                await asyncio.sleep(0)
                self.assertEqual(active_writes, 1)
                self.assertIsNotNone(self.receiver._read_waiter)
                self.assertFalse(any(
                    body[:4] == b"\x9b\x00\x00\x60" and body[4] == 1
                    for body in self.startup_bodies
                ))
                release_probe.set()
                await asyncio.wait_for(read_completed.wait(), 1)
                self.assertGreater(
                    self.receiver._startup.keepalive_responses, 0
                )
                self.assertEqual(max_active_writes, 1)
            finally:
                release_probe.set()
                self.receiver.stop()
                await asyncio.wait_for(task, 1)
        self.assertIsNone(self.receiver._read_waiter)
        self.assertIsNone(self.receiver._startup._response)

    async def test_automatic_poll_sends_reads_and_restores_passive_wire_modes(
        self,
    ):
        self.configure_startup_session()
        self.bridge.async_process_j1587.side_effect = None
        completed = asyncio.Event()
        original_write = self.client.write_gatt_char.side_effect
        report_bodies = {
            96: bytes.fromhex("9a 80 60 01 64"),
            194: bytes.fromhex("9a 80 c2 00"),
            245: bytes.fromhex("9a 80 f5 04 64 00 00 00"),
            247: bytes.fromhex("9a 80 f7 04 64 00 00 00"),
            250: bytes.fromhex("9a 80 fa 04 64 00 00 00"),
        }

        async def write(characteristic, packet, *, response):
            await original_write(characteristic, packet, response=response)
            body = packet[2:-1]
            if body[0] == 155 and body[4] == 1:
                pid = int.from_bytes(body[2:4], "big")
                if pid in report_bodies:
                    self.receiver._notification_received(
                        None, self.packet(report_bodies[pid])
                    )
            elif body == bytes.fromhex("9b 00 00 fa 00 02 03 e8 00"):
                if any(b[4] == 1 for b in self.startup_bodies if b[0] == 155):
                    completed.set()

        self.client.write_gatt_char.side_effect = write
        with (
            patch.object(self.api, "J1708_POLL_INTERVAL", 0.05),
            patch.object(self.api, "READ_WINDOW_SECONDS", 0.01),
        ):
            task = asyncio.create_task(self.receiver._async_receive_session())
            try:
                await asyncio.wait_for(completed.wait(), 1)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(self.startup_bodies[-10:], [
            b"\x9b\x00" + pid.to_bytes(2, "big") + mode
            for pid in (96, 194, 245, 247, 250)
            for mode in (
                b"\x01\x01\x00\x00\x00", b"\x00\x02\x03\xe8\x00",
            )
        ])
        reports = [
            call.args[0] for call in
            self.bridge.async_process_j1587.await_args_list
        ]
        self.assertTrue(any(
            r.pid == 96 and r.data == b"\x64" for r in reports
        ))
        self.assertTrue(any(r.pid == 194 and r.data == b"" for r in reports))
        for pid in (245, 247, 250):
            self.assertTrue(any(
                r.pid == pid and r.data == bytes.fromhex("64 00 00 00")
                for r in reports
            ))

    def configure_read(self):
        self.receiver.j1708_startup = True
        self.receiver.j1587_extended = True
        self.read_started = asyncio.Event()

        async def read(pid, *, restore=False, mid=0):
            if not restore:
                self.read_started.set()

        self.receiver._startup = SimpleNamespace(
            ready=True, async_read=AsyncMock(side_effect=read),
            disconnected=Mock(),
        )
        timer = patch.object(self.api, "READ_WINDOW_SECONDS", 0.02)
        timer.start()
        self.addCleanup(timer.stop)

    async def test_targeted_manual_read_filters_and_restores_wildcard(self):
        self.configure_read()
        self.receiver.bridge = MqttBridge(
            "coach", AsyncMock(), engine_profile="detroit_series_60_ddec_iv",
        )
        for pid, body in (
            (194, bytes.fromhex("c2 02 a8 21")),
            (243, b"\xf3\x06\x80MAKE*"),
            (439, bytes.fromhex("ff b7 02 20 03")),
            (174, bytes.fromhex("ae 02 40 01")),
        ):
            self.read_started.clear()
            task = asyncio.create_task(self.receiver.async_read(pid, mid=128))
            await self.read_started.wait()
            if pid != 243:
                await self.receiver._async_process_body(b"\x9a\x82" + body)
            await self.receiver._async_process_body(b"\x9a\x80" + body)
            result = await task
            report, = result["reports"]
            self.assertEqual(report["mid"], 128)
            self.receiver._startup.async_read.assert_any_await(pid, mid=128)
            self.receiver._startup.async_read.assert_awaited_with(
                pid, restore=True,
            )
            self.assertEqual(self.receiver._read_mid, 0)
            if pid == 194:
                match, = report["diagnostics"]["faults"][0][
                    "manufacturer_matches"
                ]
                self.assertEqual(match["code"], "46")
            elif pid == 243:
                self.assertEqual(report["identification"]["value"], "MAKE*")
            elif pid == 439:
                self.assertEqual(report["signals"][0]["value"], 100)
            else:
                self.assertFalse(report["value_decoded"])
                self.assertEqual(report["signals"], [])
                self.assertEqual(report["data"], "4001")

    async def test_wrong_source_does_not_satisfy_target_and_bad_mid_rejected(
        self,
    ):
        self.configure_read()
        for mid in (-1, 1, 127, 256, True, "128"):
            with self.assertRaisesRegex(self.home_assistant_error, "MID"):
                await self.receiver.async_read(96, mid=mid)
        task = asyncio.create_task(self.receiver.async_read(96, mid=128))
        await self.read_started.wait()
        await self.receiver._async_process_body(
            bytes.fromhex("9a 82 60 01 64"),
        )
        with self.assertRaisesRegex(self.home_assistant_error, "MID 128"):
            await task
        self.receiver._startup.async_read.assert_awaited_with(96, restore=True)

    async def test_fuel_read_collects_sources_and_updates_existing_mqtt(self):
        self.configure_read()
        published = []

        async def publish(topic, payload, retain):
            if payload not in ("online", "offline"):
                published.append((topic, json.loads(payload)))

        self.receiver.bridge = MqttBridge("coach", publish)
        task = asyncio.create_task(self.receiver.async_read(96))
        await self.read_started.wait()
        for body in (
            "9a 80 60 01 64", "9a 82 60 01 96",
            "9a 80 60 01 78", "9a 83 60 01 ff",
            "9a 80 be 02 34 12",
        ):
            await self.receiver._async_process_body(bytes.fromhex(body))
        result = await task
        self.assertEqual(result["pid"], 96)
        self.assertEqual(
            [(r["mid"], r["signals"][0]["value"])
             for r in result["reports"]],
            [(128, 60), (130, 75), (131, None)],
        )
        self.assertTrue(any(
            topic.endswith("/128/pid/96") and data["value"] == 60
            for topic, data in published
        ))
        self.receiver._startup.async_read.assert_awaited_with(96, restore=True)
        self.assertIsNone(self.receiver._read_waiter)

    async def test_diagnostic_read_distinguishes_faults_and_empty_report(self):
        self.configure_read()
        task = asyncio.create_task(self.receiver.async_read(194))
        await self.read_started.wait()
        await self.receiver._async_process_body(
            bytes.fromhex("9a 80 c2 02 64 23")
        )
        await self.receiver._async_process_body(
            bytes.fromhex("9a 82 c2 00")
        )
        result = await task
        engine, transmission = result["reports"]
        self.assertEqual(engine["diagnostics"]["faults"][0]["code"], 100)
        self.assertEqual(transmission["diagnostics"]["faults"], [])
        self.assertEqual(self.bridge.async_process_j1587.await_count, 2)
        self.receiver._startup.async_read.assert_awaited_with(
            194, restore=True
        )

    async def test_counter_reads_preserve_last_known_mqtt_on_unavailable(self):
        self.configure_read()
        published = []

        async def publish(topic, payload, retain):
            if payload not in ("online", "offline"):
                published.append((topic, json.loads(payload)))

        self.receiver.bridge = MqttBridge(
            "coach", publish, j1708_polling=True
        )
        for pid, unit, value in (
            (245, "km", 16.09344), (247, "h", 5), (250, "L", 47.317647),
        ):
            for data, expected in (
                (bytes.fromhex("64 00 00 00"), value), (b"\xff" * 4, None),
            ):
                self.read_started.clear()
                task = asyncio.create_task(self.receiver.async_read(pid))
                await self.read_started.wait()
                await self.receiver._async_process_body(
                    bytes((154, 128, pid, 4)) + data
                )
                result = await task
                self.assertEqual(result["pid"], pid)
                self.assertEqual(
                    result["reports"][0]["signals"][0]["value"], expected
                )
                states = [
                    payload for topic, payload in published
                    if topic == f"vehicle/coach/j1587/128/pid/{pid}"
                ]
                self.assertEqual(states[-1]["value"], value)
                self.assertEqual(states[-1]["unit"], unit)
                self.assertEqual(states[-1]["value_basis"], "last_observed")
                self.assertEqual(len(states), 1)
            config, = [
                payload for topic, payload in published
                if topic == (
                    "homeassistant/sensor/"
                    f"bluefire_coach_j1587_128_{pid}/config"
                )
            ]
            self.assertEqual(config["state_class"], "total_increasing")
            self.assertNotIn("expire_after", config)
            self.assertNotIn("availability_topic", config)

    async def test_read_timeout_is_not_an_empty_or_cached_fault_list(self):
        self.configure_read()
        for pid in (96, 194, 245, 247, 250):
            with self.assertRaisesRegex(
                self.home_assistant_error, "No J1708 PID",
            ):
                await self.receiver.async_read(pid)
            self.receiver._startup.async_read.assert_awaited_with(
                pid, restore=True
            )
            self.assertIsNone(self.receiver._read_waiter)

    async def test_reads_require_ready_enabled_session_and_allowed_pid(self):
        with self.assertRaisesRegex(self.home_assistant_error, "Enable J1708"):
            await self.receiver.async_read(96)
        self.configure_read()
        for attribute in ("_closed", "_paused"):
            setattr(self.receiver, attribute, True)
            with self.assertRaises(self.home_assistant_error):
                await self.receiver.async_read(96)
            setattr(self.receiver, attribute, False)
        self.receiver._startup.ready = False
        with self.assertRaises(self.home_assistant_error):
            await self.receiver.async_read(96)
        self.receiver._startup.ready = True
        for pid in (195, True, "96"):
            with self.assertRaisesRegex(
                self.home_assistant_error, "Only supported J1708",
            ):
                await self.receiver.async_read(pid)
        self.receiver._startup.async_read.assert_not_awaited()

    async def test_concurrent_read_rejected_and_cancellation_restores(self):
        self.configure_read()
        task = asyncio.create_task(self.receiver.async_read(96))
        await self.read_started.wait()
        with self.assertRaisesRegex(self.home_assistant_error, "already"):
            await self.receiver.async_read(194)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.receiver._startup.async_read.assert_awaited_with(96, restore=True)
        self.assertIsNone(self.receiver._read_waiter)

    async def test_read_write_and_restore_failures_are_explicit(self):
        self.configure_read()
        self.receiver._startup.async_read.side_effect = [
            self.bleak_error("write failed"), None,
        ]
        with self.assertRaisesRegex(self.home_assistant_error, "write failed"):
            await self.receiver.async_read(96)
        self.receiver._startup.async_read.side_effect = [
            None, self.bleak_error("restore failed"),
        ]
        with self.assertRaisesRegex(
            self.home_assistant_error, "Unable to restore passive",
        ):
            await self.receiver.async_read(96)
        self.assertTrue(self.receiver._reconnect_event.is_set())
        self.assertIsNone(self.receiver._read_waiter)
        with self.assertRaisesRegex(self.home_assistant_error, "Enable J1708"):
            await self.receiver.async_read(96)

    async def test_disconnect_aborts_read_without_old_session_writer(self):
        self.configure_read()
        task = asyncio.create_task(self.receiver.async_read(194))
        await self.read_started.wait()
        self.receiver._startup.ready = False
        # Exercise the real session-finally disconnect path.
        self.client.services = []
        with self.assertRaises(self.home_assistant_error):
            await self.receiver._async_receive_session()
        with self.assertRaisesRegex(self.home_assistant_error, "disconnected"):
            await task
        self.receiver._startup.async_read.assert_awaited_once_with(194)
        self.assertIsNone(self.receiver._read_waiter)

    async def test_restore_failure_wakes_live_session_for_reconnection(self):
        self.configure_startup_session()
        ready = asyncio.Event()
        self.bridge.async_process_j1587.side_effect = lambda _: ready.set()
        task = asyncio.create_task(self.receiver._async_receive_session())
        await asyncio.wait_for(ready.wait(), 1)
        self.receiver._reconnect_event.set()
        with self.assertRaisesRegex(self.bleak_error, "restore failed"):
            await asyncio.wait_for(task, 1)
        self.assertFalse(self.receiver._startup.ready)
        self.client.disconnect.assert_awaited_once()

    def setUp(self):
        self.bridge = SimpleNamespace(
            async_disconnected=AsyncMock(),
            async_process_pgn_report=AsyncMock(),
            async_process_j1587=AsyncMock(),
            async_process_obd_report=AsyncMock(),
        )
        self.bluetooth = SimpleNamespace(
            async_ble_device_from_address=Mock(return_value=object())
        )
        self.client = SimpleNamespace(
            services=[], disconnect=AsyncMock(), is_connected=False,
            start_notify=AsyncMock(), stop_notify=AsyncMock(),
            write_gatt_char=AsyncMock(),
        )
        self.connect = AsyncMock(return_value=self.client)
        self.home_assistant_error = type(
            "HomeAssistantError", (Exception,), {})
        self.bleak_error = type("BleakError", (Exception,), {})
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", bluetooth=self.bluetooth
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                HomeAssistantError=self.home_assistant_error,
            ),
            "bleak": module("bleak"),
            "bleak.exc": module("bleak.exc", BleakError=self.bleak_error),
            "bleak_retry_connector": module(
                "bleak_retry_connector",
                BleakClientWithServiceCache=object,
                establish_connection=self.connect,
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.module_name = "custom_components.bluefire.receiver"
        sys.modules.pop(self.module_name, None)
        self.addCleanup(sys.modules.pop, self.module_name, None)
        self.api = importlib.import_module(self.module_name)
        self.receiver = self.api.BlueFireReceiver(
            object(), "AA:BB:CC:DD:EE:01", self.bridge,
            health=Health(),
        )

    @staticmethod
    def packet(body):
        total = sum(body)
        checksum = 255 if total == 0 else 255 - ((total - 1) % 255 + 1)
        high, low = divmod(len(body), 256)
        return bytes((high, low, high ^ low)) + body + bytes((checksum,))

    async def test_pgn_notification_is_parsed_and_forwarded(self):
        body = bytes.fromhex("97 00 f0 04 06 00 08 00 00 7d 40 1f ff ff ff")
        packet = self.packet(body)
        decoded = self.receiver._decoder.feed(packet[:6])
        self.assertEqual(decoded, ())
        decoded = self.receiver._decoder.feed(packet[6:])
        for message in decoded:
            await self.receiver._async_process_body(message)
        self.bridge.async_process_pgn_report.assert_awaited_once()
        report = self.bridge.async_process_pgn_report.await_args.args[0]
        self.assertEqual(report.pgn, 61444)
        self.assertEqual(report.data, bytes.fromhex("00 00 7d 40 1f ff ff ff"))
        self.assertEqual(self.receiver.health.counters["pgn_reports"], 1)
        self.assertIsNotNone(self.receiver.health.last_data)

    async def test_configured_j1587_format_and_obd_reports_route_separately(
            self):
        self.receiver.j1587_extended = True
        await self.receiver._async_process_body(
            bytes.fromhex("9a 80 be 02 34 12")
        )
        self.bridge.async_process_j1587.assert_awaited_once()
        self.assertEqual(
            self.bridge.async_process_j1587.await_args.args[0].pid, 190
        )
        await self.receiver._async_process_body(
            bytes.fromhex("ae 07 e8 01 00 0c 02 1f 40")
        )
        self.bridge.async_process_obd_report.assert_awaited_once()
        self.assertEqual(
            self.bridge.async_process_obd_report.await_args.args[0].pid, 12
        )

    async def test_j1587_requires_explicit_firmware_format(self):
        with self.assertRaisesRegex(
            self.api.ProtocolError, "Select a J1587 firmware format"
        ):
            await self.receiver._async_process_body(
                bytes.fromhex("9a 80 be 02 34 12")
            )
        self.bridge.async_process_j1587.assert_not_awaited()
        self.assertEqual(self.receiver.health.counters["parse_errors"], 1)
        self.assertEqual(self.receiver.health.counters["unknown_commands"], 0)

    async def test_controls_and_heartbeats_never_mark_telemetry_online(self):
        for command in (255, 42):
            await self.receiver._async_process_body(bytes((command,)))
        self.bridge.async_process_pgn_report.assert_not_awaited()
        self.bridge.async_process_j1587.assert_not_awaited()
        self.bridge.async_process_obd_report.assert_not_awaited()
        self.assertEqual(self.receiver.health.counters["heartbeats"], 1)
        self.assertEqual(self.receiver.health.counters["unknown_commands"], 1)

    async def test_malformed_j1587_values_are_counted_before_side_effects(
        self,
    ):
        cases = (
            ("9a 88 c2 01 00", "Truncated J1587 diagnostic entry"),
            ("9a 00 5c 01 00", "Expected a J1587 MID"),
            ("9a 80 c2 02 64 a3", "Missing J1587 diagnostic occurrence"),
            ("9a 80 5c 02 00 00", "fixed-width PID"),
            ("9a 80 f5 03 00 00 00", "value length does not match PID"),
        )
        for index, (body, error) in enumerate(cases, 1):
            with self.subTest(body=body):
                self.receiver.j1587_extended = True
                with (
                    self.assertLogs(self.module_name, "WARNING") as logs,
                    self.assertRaisesRegex(self.api.ProtocolError, error),
                ):
                    await self.receiver._async_process_body(
                        bytes.fromhex(body)
                    )
                self.assertIn(error, logs.output[0])
                self.assertEqual(
                    self.receiver.health.counters["parse_errors"], index
                )
                self.assertEqual(self.receiver.health.counters["packets"], 0)
                self.assertEqual(
                    self.receiver.health.counters["j1587_reports"], 0
                )
                self.assertIsNone(self.receiver.health.last_data)
                self.assertFalse(self.receiver._session_healthy)
                self.bridge.async_process_j1587.assert_not_awaited()

    async def test_valid_j1587_does_not_mask_bridge_failures(self):
        self.receiver.j1587_extended = True
        self.bridge.async_process_j1587.side_effect = ValueError(
            "publisher failure"
        )
        with self.assertRaisesRegex(ValueError, "publisher failure"):
            await self.receiver._async_process_body(
                bytes.fromhex("9a 80 5c 01 00")
            )
        self.assertEqual(self.receiver.health.counters["parse_errors"], 0)

    async def test_bad_j1587_reports_keep_live_session_and_read_open(self):
        self.configure_startup_session(report_on_start=False)
        messages = []
        received = asyncio.Event()

        async def publish(topic, payload, retain):
            messages.append((topic, payload, retain))
            if topic == "vehicle/coach/j1587/136/faults/194":
                received.set()

        self.receiver.bridge = MqttBridge("coach", publish)
        with (
            self.assertLogs(self.module_name, level="WARNING") as logs,
            patch.object(self.api, "READ_WINDOW_SECONDS", 0.1),
        ):
            task = asyncio.create_task(self.receiver.async_run())
            read = None
            try:
                async with asyncio.timeout(1):
                    while not (
                        self.receiver._startup and self.receiver._startup.ready
                    ):
                        await asyncio.sleep(0)
                read = asyncio.create_task(self.receiver.async_read(194))
                async with asyncio.timeout(1):
                    while self.receiver._read_waiter is None:
                        await asyncio.sleep(0)
                bad = (
                    bytes.fromhex("0005059a88c2010019")
                    + bytes.fromhex("0005059a005c010008")
                )
                self.receiver._notification_received(None, bad)
                async with asyncio.timeout(1):
                    while self.receiver.health.counters["parse_errors"] < 2:
                        await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertFalse(read.done())
                self.assertEqual(self.receiver._read_reports, {})
                self.assertIsNone(self.receiver.health.last_data)
                self.assertEqual(messages, [])
                self.receiver._notification_received(
                    None,
                    self.packet(bytes.fromhex("9a 80 5c 01 00"))
                    + bad
                    + self.packet(bytes.fromhex("9a 88 c2 02 64 23")),
                )
                await asyncio.wait_for(received.wait(), 1)
                result = await asyncio.wait_for(read, 1)
                self.assertEqual(result["reports"][0]["mid"], 136)
                self.assertEqual(
                    result["reports"][0]["diagnostics"]["fault_count"], 1
                )
                self.assertFalse(task.done())
                self.assertTrue(self.receiver._startup.ready)
                self.client.disconnect.assert_not_awaited()
                self.assertEqual(self.connect.await_count, 1)
                self.assertEqual(
                    self.receiver.health.counters["connection_errors"], 0
                )
                self.assertEqual(
                    self.receiver.health.counters["j1587_reports"], 2
                )
                self.assertEqual(
                    self.receiver.health.counters["parse_errors"], 4
                )
                self.assertEqual(
                    len([topic for topic, _, _ in messages
                         if topic.endswith("/faults/194")]), 1
                )
            finally:
                if read is not None and not read.done():
                    read.cancel()
                    await asyncio.gather(read, return_exceptions=True)
                self.receiver.stop()
                await asyncio.wait_for(task, 1)
        self.assertEqual(len(logs.output), 4)

    async def test_notification_callback_overflow_signals_reconnect(self):
        self.receiver._queue = __import__("asyncio").Queue(maxsize=1)
        self.receiver._queue.put_nowait(b"pending")
        self.receiver._notification_received(None, bytearray(b"next"))
        self.assertTrue(self.receiver._overflow.is_set())

    async def test_missing_device_fails_without_connection_attempt(self):
        self.bluetooth.async_ble_device_from_address.return_value = None
        with self.assertRaisesRegex(
            self.home_assistant_error, "not visible"
        ):
            await self.receiver._async_receive_session()
        self.connect.assert_not_awaited()

    async def test_unrecognized_service_is_rejected_and_disconnected(self):
        self.client.services = []
        with self.assertRaisesRegex(self.home_assistant_error, "service"):
            await self.receiver._async_receive_session()
        self.client.disconnect.assert_awaited_once()

    async def test_supported_notify_characteristics_are_selected(self):
        service = SimpleNamespace(
            uuid=self.api.EZ_SERVICE,
            characteristics=[
                SimpleNamespace(
                    uuid=self.api.EZ_RECEIVE, properties=["notify"]
                ),
                SimpleNamespace(
                    uuid=self.api.EZ_CLIENT_WRITE, properties=["write"]
                ),
            ],
        )
        self.client.services = [service]
        with self.assertRaises(self.bleak_error):
            await self.receiver._async_receive_session()
        self.client.start_notify.assert_awaited_once()
        self.client.stop_notify.assert_awaited_once()
        self.client.write_gatt_char.assert_not_awaited()

    async def test_indicate_characteristics_are_supported(self):
        service = SimpleNamespace(
            uuid=self.api.EZ_SERVICE,
            characteristics=[
                SimpleNamespace(
                    uuid=self.api.EZ_RECEIVE, properties=["indicate"]
                ),
            ],
        )
        self.client.services = [service]
        with self.assertRaises(self.bleak_error):
            await self.receiver._async_receive_session()
        self.client.start_notify.assert_awaited_once()

    async def test_session_consumes_ez_stream_and_cleans_up(self):
        body = bytes.fromhex("97 00 f0 04 06 00 08 00 00 7d 40 1f ff ff ff")
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[characteristic],
            )
        ]
        self.client.is_connected = True
        self.bridge.async_process_pgn_report.side_effect = (
            lambda _report: setattr(self.client, "is_connected", False)
        )
        self.client.start_notify.side_effect = (
            lambda char, callback: callback(char, self.packet(body))
        )
        self.client.stop_notify.side_effect = self.bleak_error("stop failed")
        self.client.disconnect.side_effect = self.bleak_error(
            "disconnect failed"
        )
        with self.assertRaises(self.bleak_error):
            await self.receiver._async_receive_session()
        self.assertEqual(
            self.receiver.services,
            [{
                "uuid": self.api.EZ_SERVICE,
                "characteristics": [{
                    "uuid": self.api.EZ_RECEIVE,
                    "properties": ["notify"],
                }],
            }],
        )
        self.bridge.async_process_pgn_report.assert_awaited_once()
        self.client.stop_notify.assert_awaited_once_with(characteristic)
        self.client.disconnect.assert_awaited_once()

    async def test_diagnostic_pause_closes_connection_without_offline_publish(
        self,
    ):
        ready = asyncio.Event()
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[characteristic],
            )
        ]
        self.client.is_connected = True

        async def start_notify(*_args):
            ready.set()

        self.client.start_notify.side_effect = start_notify

        with patch(
            "custom_components.bluefire.receiver.asyncio.sleep",
            new=AsyncMock(),
        ):
            task = asyncio.create_task(self.receiver.async_run())
            await asyncio.wait_for(ready.wait(), 1)
            await self.receiver.async_pause()
            self.client.disconnect.assert_awaited_once()
            self.bridge.async_disconnected.assert_not_awaited()
            self.receiver.async_resume()
            self.receiver.stop()
            await asyncio.wait_for(task, 1)

    async def test_no_notify_characteristic_is_rejected(self):
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[
                    SimpleNamespace(
                        uuid=self.api.EZ_RECEIVE, properties=["read"]
                    )
                ],
            )
        ]
        with self.assertRaisesRegex(self.home_assistant_error, "notification"):
            await self.receiver._async_receive_session()
        self.client.disconnect.assert_awaited_once()

    async def test_receiver_retries_failures_with_backoff(self):
        async def session():
            if self.receiver._async_receive_session.await_count == 1:
                raise self.api.ProtocolError("bad packet")
            self.receiver.stop()
            raise self.bleak_error("disconnected")

        self.receiver._async_receive_session = AsyncMock(side_effect=session)
        self.bridge.async_disconnected.side_effect = [
            RuntimeError("MQTT offline"), None,
        ]
        with patch(
            "custom_components.bluefire.receiver.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep:
            await self.receiver.async_run()
        self.assertEqual(self.receiver._async_receive_session.await_count, 2)
        sleep.assert_awaited_once_with(self.api.RECONNECT_MIN)
        self.bridge.async_disconnected.assert_awaited()
        self.assertEqual(self.receiver.health.counters["framing_errors"], 1)
        self.assertEqual(self.receiver.health.counters["connection_errors"], 1)

    async def test_healthy_session_resets_backoff_after_startup_failures(self):
        async def session():
            attempt = self.receiver._async_receive_session.await_count
            self.receiver._session_healthy = attempt == 4
            if attempt == 6:
                self.receiver.stop()
            raise self.bleak_error("disconnected")

        self.receiver._async_receive_session = AsyncMock(side_effect=session)
        with patch.object(self.api.asyncio, "sleep", new=AsyncMock()) as sleep:
            await self.receiver.async_run()
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list], [2, 4, 8, 2, 4]
        )
        events = self.receiver.connection_diagnostics()["events"]
        self.assertEqual(events[-1]["event"], "disconnected")
        self.assertEqual(events[-1]["reason"], "disconnected")

    async def test_malformed_frame_increments_framing_error_once(self):
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[characteristic],
            )
        ]
        self.client.is_connected = True
        malformed = bytearray(self.packet(b"\xff"))
        malformed[2] ^= 1
        self.client.start_notify.side_effect = (
            lambda char, callback: callback(char, malformed)
        )
        cleanup_snapshots = []

        async def stop_notify(_characteristic):
            cleanup_snapshots.append(self.receiver.connection_diagnostics())

        self.client.stop_notify.side_effect = stop_notify

        async def stop_after_failure(_delay):
            self.receiver.stop()

        with patch(
            "custom_components.bluefire.receiver.asyncio.sleep",
            new=AsyncMock(side_effect=stop_after_failure),
        ), patch.object(
            self.api, "RECEIVE_ERROR_LIMIT", 1,
        ):
            await self.receiver.async_run()

        self.assertEqual(self.receiver.health.counters["framing_errors"], 1)
        history = self.receiver.connection_diagnostics()["connection_history"]
        self.assertEqual(len(history), 1)
        record = history[0]
        self.assertIn("Too many malformed", record["reason"])
        self.assertIsNotNone(record["connected_at"])
        self.assertIsNotNone(record["ended_at"])
        self.assertIsNone(record["ready_at"])
        self.assertEqual(record["context"]["exception_type"], "BleakError")
        self.assertEqual(record["context"]["counters"]["framing_errors"], 1)
        cleanup_record = cleanup_snapshots[0]["connection_history"][0]
        self.assertEqual(cleanup_record["reason"], record["reason"])
        self.assertEqual(
            cleanup_record["context"]["exception_type"], "BleakError"
        )
        self.assertIsNotNone(cleanup_record["ended_at"])
        self.assertEqual(
            record["context"]["recent_notifications"][0]["hex"],
            malformed.hex(),
        )

    async def test_history_retains_last_ten_attempts_with_separate_counters(
        self,
    ):
        async def session():
            self.receiver.health.count("notifications")
            if self.receiver._async_receive_session.await_count == 12:
                self.receiver.stop()
            raise self.bleak_error("link lost")

        self.receiver._async_receive_session = AsyncMock(side_effect=session)
        with patch.object(self.api.asyncio, "sleep", new=AsyncMock()):
            await self.receiver.async_run()
        history = self.receiver.connection_diagnostics()["connection_history"]
        self.assertEqual(len(history), 10)
        self.assertEqual([item["attempt"] for item in history],
                         list(range(3, 13)))
        self.assertEqual(history[0]["retry_delay_s"], 8)
        self.assertIsNone(history[-1]["retry_delay_s"])
        for record in history:
            self.assertEqual(record["end_event"], "disconnected")
            self.assertEqual(record["reason"], "link lost")
            self.assertEqual(record["context"]["counters"]["notifications"], 1)
            self.assertEqual(
                record["context"]["counters"]["connection_errors"], 1
            )
            self.assertIsNone(record["connected_at"])
            self.assertEqual(
                record["context"]["exception_type"], "BleakError"
            )

    def test_notification_history_is_bounded_and_excludes_authentication(self):
        self.receiver._connection_event("connecting")
        self.receiver._startup = SimpleNamespace(ready=False)
        self.receiver._notification_received(None, b"authentication")
        self.assertEqual(len(self.receiver._recent_notifications), 0)
        self.receiver._startup = None
        characteristic = SimpleNamespace(uuid=self.api.EZ_RECEIVE, handle=16)
        for value in range(12):
            self.receiver._notification_received(
                characteristic, bytes((value,)) * 600
            )
        self.receiver._connection_event("disconnected", "test")
        record = self.receiver.connection_diagnostics()[
            "connection_history"
        ][0]
        notifications = record["context"]["recent_notifications"]
        self.assertEqual(len(notifications), 10)
        self.assertEqual(notifications[0]["hex"], (b"\x02" * 512).hex())
        self.assertTrue(notifications[0]["truncated"])
        self.assertEqual(notifications[0]["length"], 600)
        self.assertEqual(notifications[0]["characteristic"],
                         self.api.EZ_RECEIVE)
        self.assertEqual(notifications[0]["handle"], 16)
        notifications[0]["hex"] = "changed by caller"
        self.receiver._connection_event("connecting")
        self.receiver._connection_event("disconnected", "another test")
        history = self.receiver.connection_diagnostics()["connection_history"]
        self.assertEqual(history[0]["context"]["recent_notifications"][0][
            "hex"
        ], (b"\x02" * 512).hex())
        self.assertEqual(history[1]["context"]["recent_notifications"], [])

    def test_disconnect_context_records_queue_fragments_and_bluetooth(self):
        self.receiver._connection_event("connecting")
        self.receiver._decoder.feed(b"\x00")
        self.receiver._control_decoder.feed(b"\x00\x01")
        self.receiver._queue = asyncio.Queue(maxsize=1)
        self.receiver._queue.put_nowait(b"queued")
        self.receiver._overflow.set()
        self.receiver.health.advertisement(-76, "scanner")
        self.receiver.health.data_seen()
        self.receiver._last_write = {
            "time": "write time", "command": 7, "length": 4,
        }
        self.receiver._connection_event("disconnected", "stream failed")
        context = self.receiver.connection_diagnostics()[
            "connection_history"
        ][0]["context"]
        self.assertEqual(context["pending_bytes"], 1)
        self.assertEqual(context["control_pending_bytes"], 2)
        self.assertEqual(context["queue_depth"], 1)
        self.assertEqual(context["queue_capacity"], 1)
        self.assertTrue(context["queue_overflow"])
        self.assertEqual(context["bluetooth"]["rssi"], -76)
        self.assertEqual(context["bluetooth"]["source"], "scanner")
        self.assertIsNotNone(context["bluetooth"]["last_advertisement"])
        self.assertIsNotNone(context["last_data"])
        self.assertEqual(context["last_write"]["command"], 7)
        self.assertGreaterEqual(context["duration_s"], 0)

    def test_connection_history_without_health(self):
        self.receiver.health = None
        self.receiver._connection_event("connecting")
        self.receiver._connection_event("disconnected", "test")
        context = self.receiver.connection_diagnostics()[
            "connection_history"
        ][0]["context"]
        self.assertIsNone(context["bluetooth"])
        self.assertIsNone(context["last_data"])
        self.assertEqual(context["counters"], {})

    async def test_isolated_corruption_recovers_without_reconnecting(self):
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [SimpleNamespace(
            uuid=self.api.EZ_SERVICE, characteristics=[characteristic],
        )]
        self.client.is_connected = True
        self.receiver.j1587_extended = True
        report = self.packet(bytes.fromhex("9a 80 be 02 a0 0f"))
        chunk = report + b"\x00\x05\x05" + report + self.packet(b"\xff")
        self.client.start_notify.side_effect = (
            lambda char, callback: callback(char, chunk)
        )
        received = asyncio.Event()

        async def publish(_report):
            if self.bridge.async_process_j1587.await_count == 2:
                received.set()

        self.bridge.async_process_j1587.side_effect = publish
        task = asyncio.create_task(self.receiver.async_run())
        try:
            await asyncio.wait_for(received.wait(), 1)
            self.assertFalse(task.done())
            self.client.disconnect.assert_not_awaited()
            self.assertEqual(self.connect.await_count, 1)
            self.assertEqual(self.receiver.health.counters["framing_errors"],
                             1)
            self.assertEqual(
                self.receiver.health.counters["connection_errors"], 0
            )
            stream = self.receiver.connection_diagnostics()["receive_stream"]
            self.assertEqual(stream["resynchronizations"], 1)
            self.assertFalse(stream["resynchronizing"])
            self.assertTrue(self.receiver._receive_is_recent())
        finally:
            self.receiver.stop()
            await asyncio.wait_for(task, 1)

    def test_corruption_budget_is_bounded_and_old_errors_expire(self):
        chunk = b"\x7f\x00\x00" + self.packet(b"\xff") * 2
        with patch.object(self.api, "monotonic", return_value=0):
            for _ in range(9):
                self.receiver._decoder.feed(chunk)
                self.receiver._record_stream_errors()
            self.assertEqual(self.receiver.health.counters["framing_errors"],
                             9)
            self.receiver._decoder.feed(chunk)
            with self.assertRaisesRegex(self.bleak_error, "10 in 10 seconds"):
                self.receiver._record_stream_errors()
        with patch.object(self.api, "monotonic", return_value=11):
            self.receiver._decoder.feed(chunk)
            self.receiver._record_stream_errors()
            stream = self.receiver.connection_diagnostics()["receive_stream"]
            self.assertEqual(stream["recent_framing_errors"], 1)

    def test_startup_corruption_uses_the_same_bounded_recovery(self):
        self.receiver._startup = SimpleNamespace(ready=False)
        self.receiver._decoder.feed(b"\x7f\x00\x00")
        self.receiver._record_stream_errors()
        self.assertEqual(self.receiver.health.counters["framing_errors"], 1)
        self.assertTrue(self.receiver._decoder.resynchronizing)
        for _ in range(self.api.RECEIVE_ERROR_LIMIT - 2):
            self.receiver._decoder.feed(self.packet(b"\xff") * 2)
            self.receiver._decoder.feed(b"\x7f\x00\x00")
            self.receiver._record_stream_errors()
        self.receiver._decoder.feed(self.packet(b"\xff") * 2)
        self.receiver._decoder.feed(b"\x7f\x00\x00")
        with self.assertRaisesRegex(self.bleak_error, "Too many malformed"):
            self.receiver._record_stream_errors()

    async def test_persistent_corruption_without_valid_packets_times_out(self):
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [SimpleNamespace(
            uuid=self.api.EZ_SERVICE, characteristics=[characteristic],
        )]
        self.client.is_connected = True
        self.client.start_notify.side_effect = (
            lambda char, callback: callback(char, bytes(128))
        )
        with patch.object(self.api, "RECEIVE_SILENCE_TIMEOUT", 0.01):
            with self.assertRaisesRegex(
                self.bleak_error, "No valid BlueFire receive packets"
            ):
                await asyncio.wait_for(
                    self.receiver._async_receive_session(), 2
                )
        self.client.disconnect.assert_awaited_once()
        self.assertIsNone(self.receiver._last_valid_packet)
        self.assertEqual(self.receiver.health.counters["framing_errors"], 1)

    def test_receive_activity_requires_valid_packets_and_expires(self):
        with patch.object(self.api, "monotonic", return_value=0):
            self.receiver._notification_received(None, bytes(128))
            self.assertFalse(self.receiver._receive_is_recent())
            self.receiver._notification_received(
                None, self.packet(b"\xff") * 2
            )
            self.assertTrue(self.receiver._receive_is_recent())
        with patch.object(self.api, "monotonic", return_value=30):
            self.assertFalse(self.receiver._receive_is_recent())

    async def test_connection_timeout_has_a_reason_and_retains_retries(self):
        async def connect(*_args, **_kwargs):
            await asyncio.Future()

        self.connect.side_effect = connect
        with (
            patch.object(self.api, "CONNECTION_TIMEOUT", 0.01),
            patch.object(
                self.api.asyncio, "sleep", new=AsyncMock(
                    side_effect=lambda _: self.receiver.stop()
                ),
            ) as sleep,
            self.assertLogs(self.module_name, level="WARNING") as logs,
        ):
            await asyncio.wait_for(self.receiver.async_run(), 1)
        history = self.receiver.connection_diagnostics()["connection_history"]
        reason = (
            "BlueFire Bluetooth connection timed out (limit: 0.01 seconds)"
        )
        self.assertEqual(history[0]["reason"], reason)
        self.assertEqual(history[0]["context"]["exception_message"], reason)
        self.assertEqual(
            history[0]["context"]["exception_type"], "TimeoutError"
        )
        self.assertEqual(history[0]["retry_delay_s"], self.api.RECONNECT_MIN)
        self.assertEqual(self.receiver.health.counters["connection_errors"], 1)
        self.assertIn(reason, logs.output[0])
        sleep.assert_awaited_once_with(self.api.RECONNECT_MIN)
        self.client.start_notify.assert_not_awaited()

    async def test_connected_session_is_not_limited_by_connect_timeout(self):
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[characteristic],
            )
        ]
        self.client.is_connected = True
        with patch.object(self.api, "CONNECTION_TIMEOUT", 0.01):
            task = asyncio.create_task(self.receiver._async_receive_session())
            await asyncio.sleep(0.05)
            self.assertFalse(task.done())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.client.disconnect.assert_awaited_once()

    async def test_stop_interrupts_idle_session_and_disconnects(self):
        ready = asyncio.Event()
        characteristic = SimpleNamespace(
            uuid=self.api.EZ_RECEIVE, properties=["notify"]
        )
        self.client.services = [
            SimpleNamespace(
                uuid=self.api.EZ_SERVICE,
                characteristics=[characteristic],
            )
        ]
        self.client.is_connected = True

        async def start_notify(*_args):
            ready.set()

        self.client.start_notify.side_effect = start_notify
        task = asyncio.create_task(self.receiver.async_run())
        await asyncio.wait_for(ready.wait(), 1)
        self.receiver.stop()
        await asyncio.wait_for(task, 1)
        self.client.disconnect.assert_awaited_once()

    async def test_receiver_stops_cleanly_after_session_returns(self):
        async def session():
            self.receiver.stop()

        self.receiver._async_receive_session = AsyncMock(side_effect=session)
        await self.receiver.async_run()
        self.bridge.async_disconnected.assert_awaited_once()

    async def test_receiver_propagates_cancellation_after_cleanup(self):
        self.receiver._async_receive_session = AsyncMock(
            side_effect=asyncio.CancelledError
        )
        with self.assertRaises(asyncio.CancelledError):
            await self.receiver.async_run()
        self.bridge.async_disconnected.assert_awaited_once()

    def configure_startup_session(
        self, overrides=None, *, report_on_start=True,
        report_body=bytes.fromhex("9a 80 be 02 a0 0f"),
    ):
        self.receiver.j1708_startup = True
        self.receiver.j1587_extended = True
        self.bluetooth.async_ble_device_from_address.return_value = (
            SimpleNamespace(name="BlueFire EZ")
        )
        self.client.is_connected = True
        self.write_characteristic = SimpleNamespace(
            uuid=self.api.EZ_CLIENT_WRITE, properties=["write", "indicate"]
        )
        self.client.services = [SimpleNamespace(
            uuid=self.api.EZ_SERVICE,
            characteristics=[
                self.write_characteristic,
                SimpleNamespace(
                    uuid=self.api.EZ_RECEIVE, properties=["notify"]
                ),
            ],
        )]
        self.startup_bodies = []
        responses = {
            0: bytes((3, 23, 4, 1, 0)) + bytes(16),
            9: b"\x01", 130: b"\x01", 171: b"\x01",
            206: bytes(15), 7: b"\x01", 8: b"",
        }
        responses.update(overrides or {})

        async def subscribe(characteristic, callback):
            if characteristic.uuid == self.api.EZ_RECEIVE:
                callback(characteristic, self.packet(b"\xff"))
                callback(
                    characteristic,
                    self.packet(report_body),
                )

        async def write(characteristic, packet, *, response):
            self.assertIs(characteristic, self.write_characteristic)
            self.assertIs(response, True)
            self.assertEqual(sum(packet) % 255, 0)
            self.assertLessEqual(len(packet), 20)
            body = packet[2:-1]
            self.startup_bodies.append(body)
            data = responses.get(body[0])
            if body[0] == 153:
                data = body[1:]
            if data is not None:
                reply = self.packet(bytes((body[0],)) + data)
                if body == b"\x99\x01" and report_on_start:
                    reply += self.packet(report_body)
                self.receiver._notification_received(None, reply)

        self.client.start_notify.side_effect = subscribe
        self.client.write_gatt_char.side_effect = write
        self.bridge.async_process_j1587.side_effect = (
            lambda _: setattr(self.client, "is_connected", False)
        )

    async def test_live_startup_routes_only_authenticated_j1708_reports(self):
        self.configure_startup_session()
        for _ in range(2):
            self.client.is_connected = True
            with self.assertRaises(self.bleak_error):
                await asyncio.wait_for(
                    self.receiver._async_receive_session(), 2
                )
            diagnostics = self.receiver.startup_diagnostics()
            self.assertEqual(diagnostics["stage"], "disconnected")
            self.assertEqual(diagnostics["firmware"], [3, 23, 0])
            self.assertEqual(diagnostics["subscriptions_sent"], len(ENTITIES))
            self.assertEqual(diagnostics["discarded_reports"], 1)
        self.assertEqual(self.bridge.async_process_j1587.await_count, 2)
        self.assertEqual(self.startup_bodies.count(b"\x00"), 2)
        self.assertEqual(self.startup_bodies.count(b"\x99\x01"), 2)
        for pid in (234, 237, 243):
            self.assertEqual(self.startup_bodies.count(
                b"\x9b\x00" + pid.to_bytes(2, "big")
                + b"\x01\x01\x00\x00\x00"
            ), 2)
        self.assertEqual(self.client.disconnect.await_count, 2)
        self.assertEqual(self.receiver._decoder.pending_bytes, 0)

    async def test_startup_recovers_initial_fragment_and_negotiation_noise(
        self,
    ):
        for command in (None, 0, 9, 130, 153):
            with self.subTest(command=command):
                self.configure_startup_session()
                original_subscribe = self.client.start_notify.side_effect
                original_write = self.client.write_gatt_char.side_effect
                errors_before = self.receiver.health.counters["framing_errors"]
                injected = False

                def noise():
                    nonlocal injected
                    injected = True
                    self.receiver._notification_received(
                        None, b"\x7f\x00\x00" + self.packet(b"\xff") * 2
                    )

                async def subscribe(characteristic, callback):
                    if command is None and not injected:
                        noise()
                    await original_subscribe(characteristic, callback)

                async def write(characteristic, packet, *, response):
                    if command == packet[2] and not injected:
                        noise()
                    await original_write(
                        characteristic, packet, response=response
                    )

                self.client.start_notify.side_effect = subscribe
                self.client.write_gatt_char.side_effect = write
                self.bridge.async_process_j1587.reset_mock()
                with self.assertRaisesRegex(
                    self.bleak_error, "Bluetooth connection lost"
                ):
                    await asyncio.wait_for(
                        self.receiver._async_receive_session(), 2
                    )
                self.assertTrue(injected)
                self.assertEqual(
                    self.receiver.health.counters["framing_errors"],
                    errors_before + 1,
                )
                self.assertEqual(self.startup_bodies.count(b"\x99\x01"), 1)
                self.bridge.async_process_j1587.assert_awaited_once()
        self.assertEqual(self.client.disconnect.await_count, 5)
        self.assertEqual(self.receiver._decoder.pending_bytes, 0)

    async def test_authentication_rejection_is_visible_and_never_starts_data(
        self,
    ):
        self.configure_startup_session(overrides={130: b"\x00"})
        with self.assertRaisesRegex(
            self.home_assistant_error, "authentication_1 rejected"
        ):
            await asyncio.wait_for(
                self.receiver._async_receive_session(), 2
            )
        self.assertEqual(
            self.receiver.startup_diagnostics()["stage"], "failed"
        )
        self.assertNotIn(b"\x99\x01", self.startup_bodies)
        self.bridge.async_process_j1587.assert_not_awaited()
        self.client.disconnect.assert_awaited_once()

    async def test_startup_to_real_mqtt_bridge_publishes_1000_rpm(self):
        self.configure_startup_session()
        await self.assert_startup_publishes_real_mqtt_state()
        self.assertTrue(
            self.receiver.startup_diagnostics()["j1708_available"]
        )

    async def test_startup_identification_replies_reach_mqtt_and_diagnostics(
        self,
    ):
        for extended in (False, True):
            with self.subTest(extended=extended):
                self.configure_startup_session(
                    overrides={
                        0: bytes((3, 23 if extended else 18, 4, 1, 0))
                        + bytes(16),
                    },
                    report_on_start=False,
                )
                self.receiver.j1587_extended = extended
                write = self.client.write_gatt_char.side_effect
                fixtures = {
                    234: (128, b"EXAMPLE ECU SOFTWARE REV A"),
                    237: (128, b"EXAMPLE VIN"),
                    243: (130, b"EXAMPLE TRANSMISSION*MODEL*SERIAL*"),
                }
                messages = {}
                received = asyncio.Event()

                async def identify(characteristic, packet, *, response):
                    await write(characteristic, packet, response=response)
                    body = packet[2:-1]
                    if body[0] != 155 or body[4] != 1:
                        return
                    pid = int.from_bytes(body[2:4], "big")
                    if pid not in fixtures:
                        return
                    mid, text = fixtures[pid]
                    pid_bytes = (
                        bytes((pid,)) if extended else pid.to_bytes(2, "big")
                    )
                    reply = self.packet(
                        bytes((154, mid)) + pid_bytes
                        + bytes((len(text),)) + text
                    )
                    for offset in range(0, len(reply), 20):
                        self.receiver._notification_received(
                            None, reply[offset:offset + 20]
                        )

                async def publish(topic, payload, retain):
                    messages[topic] = (payload, retain)
                    if topic == "vehicle/coach/j1587/130/pid/243":
                        received.set()

                self.client.write_gatt_char.side_effect = identify
                self.receiver.bridge = MqttBridge("coach", publish)
                task = asyncio.create_task(
                    self.receiver._async_receive_session()
                )
                try:
                    await asyncio.wait_for(received.wait(), 2)
                    self.assertTrue(self.receiver._startup.ready)
                    self.assertEqual(
                        self.receiver.startup_diagnostics()[
                            "identification_requests_sent"], 3
                    )
                    for pid, (mid, text) in fixtures.items():
                        payload, retain = messages[
                            f"vehicle/coach/j1587/{mid}/pid/{pid}"
                        ]
                        self.assertTrue(retain)
                        state = json.loads(payload)
                        self.assertEqual(state["value"], text.decode("ascii"))
                        self.assertEqual(state["identity_basis"],
                                         "controller_reported")
                    identity = self.receiver.bridge.diagnostics()["j1587"][
                        "controller_identification"
                    ]
                    self.assertEqual(identity["130"]["243"]["value"],
                                     fixtures[243][1].decode("ascii"))
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

    async def test_initially_unavailable_bus_still_publishes_real_mqtt_state(
        self,
    ):
        self.configure_startup_session(overrides={7: b"\x00"})
        await self.assert_startup_publishes_real_mqtt_state()
        self.assertFalse(
            self.receiver.startup_diagnostics()["j1708_available"]
        )

    async def assert_startup_publishes_real_mqtt_state(self):
        messages = []

        async def publish(topic, payload, retain):
            self.assertTrue(self.receiver._startup.ready)
            messages.append((topic, payload, retain))
            if topic == "vehicle/coach/j1587/128/pid/190":
                self.client.is_connected = False

        self.receiver.bridge = MqttBridge("coach", publish)
        with self.assertRaises(self.bleak_error):
            await asyncio.wait_for(
                self.receiver._async_receive_session(), 2
            )
        states = [
            (json.loads(payload), retain)
            for topic, payload, retain in messages
            if topic == "vehicle/coach/j1587/128/pid/190"
        ]
        self.assertEqual(len(states), 1)
        state, retain = states[0]
        self.assertEqual(state["value"], 1000)
        self.assertEqual(state["unit"], "rpm")
        self.assertEqual(state["datalink"], "j1708")
        self.assertFalse(retain)
        self.assertIn(
            ("vehicle/coach/j1587/availability", "online", True),
            messages,
        )
        self.assertFalse(any(
            topic.startswith("vehicle/coach/j1939")
            for topic, _, _ in messages
        ))
        diagnostics = self.receiver.startup_diagnostics()
        self.assertIsNone(diagnostics["error"])
        self.assertEqual(diagnostics["subscriptions_sent"], len(ENTITIES))
        self.assertEqual(self.receiver.health.counters["connection_errors"], 0)

    async def test_expanded_subscription_publishes_transmission_temperature(
        self,
    ):
        self.configure_startup_session(
            report_body=bytes.fromhex("9a 82 b1 02 50 03"),
        )
        messages = {}

        async def publish(topic, payload, retain):
            self.assertTrue(self.receiver._startup.ready)
            messages[topic] = payload
            if topic == "vehicle/coach/j1587/130/pid/177":
                self.client.is_connected = False

        self.receiver.bridge = MqttBridge("coach", publish)
        with self.assertRaises(self.bleak_error):
            await asyncio.wait_for(self.receiver._async_receive_session(), 2)
        self.assertIn(
            bytes.fromhex("9b 00 00 b1 00 02 03 e8 00"),
            self.startup_bodies,
        )
        state = json.loads(messages["vehicle/coach/j1587/130/pid/177"])
        self.assertEqual(
            (state["mid"], state["pid"], state["value"], state["unit"]),
            (130, 177, 100, "°C"),
        )
        config = json.loads(messages[
            "homeassistant/sensor/bluefire_coach_j1587_130_177/config"
        ])
        self.assertEqual(config["device_class"], "temperature")
        self.assertEqual(config["unit_of_measurement"], "°C")
        self.assertEqual(self.receiver._startup.subscriptions_sent,
                         len(ENTITIES))
        self.assertEqual(self.receiver._startup.discarded_reports, 1)

    async def test_unavailable_status_without_telemetry_never_publishes_online(
        self,
    ):
        self.configure_startup_session(
            overrides={7: b"\x00"}, report_on_start=False,
        )
        publish = AsyncMock()
        self.receiver.bridge = MqttBridge("coach", publish)
        task = asyncio.create_task(self.receiver._async_receive_session())
        try:
            async with asyncio.timeout(2):
                while (
                    self.receiver._startup is None
                    or not self.receiver._startup.ready
                ):
                    if task.done():
                        task.result()
                        self.fail("Session ended before report setup")
                    await asyncio.sleep(0)
            self.assertFalse(self.receiver._startup.j1708_available)
            self.assertEqual(self.receiver._startup.discarded_reports, 1)
            self.assertFalse(task.done())
            publish.assert_not_awaited()
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_startup_timeout_is_visible_and_disconnects(self):
        self.configure_startup_session(overrides={0: None})
        with patch(
            "custom_components.bluefire.startup.STEP_TIMEOUT", 0.2
        ):
            with self.assertRaisesRegex(
                self.home_assistant_error, "Timed out during version"
            ):
                await asyncio.wait_for(
                    self.receiver._async_receive_session(), 2
                )
        self.client.disconnect.assert_awaited_once()
        self.assertIn(
            "version", self.receiver.startup_diagnostics()["error"]
        )

    async def test_live_startup_errors_reach_health_and_offline_state(self):
        self.configure_startup_session(overrides={9: b"\x00"})
        real_sleep = asyncio.sleep

        async def sleep(delay):
            if delay:
                self.receiver.stop()
            else:
                await real_sleep(0)

        with patch.object(self.api.asyncio, "sleep", new=sleep):
            await asyncio.wait_for(self.receiver.async_run(), 2)
        self.assertEqual(self.receiver.health.counters["connection_errors"], 1)
        self.assertIn(
            "compatibility rejected", self.receiver.health.last_error
        )
        self.bridge.async_disconnected.assert_awaited_once()
        self.bridge.async_process_j1587.assert_not_awaited()

    async def test_ready_session_keeps_listening_without_repeating_startup(
        self,
    ):
        self.configure_startup_session()
        received = asyncio.Event()
        self.bridge.async_process_j1587.side_effect = lambda _: received.set()
        task = asyncio.create_task(self.receiver.async_run())
        try:
            await asyncio.wait_for(received.wait(), 2)
            self.receiver._notification_received(None, self.packet(b"\xff"))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertTrue(self.receiver._startup.ready)
            self.assertEqual(self.startup_bodies.count(b"\x00"), 1)
            self.assertFalse(task.done())
        finally:
            self.receiver.stop()
            await asyncio.wait_for(task, 1)

    async def test_periodic_probes_keep_telemetry_flowing_without_reauth(self):
        self.configure_startup_session()
        probed = asyncio.Event()
        write = self.client.write_gatt_char.side_effect

        async def probe(*args, **kwargs):
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                self.receiver._notification_received(
                    None, self.packet(bytes.fromhex("9a 80 be 02 a0 0f"))
                )
            await write(*args, **kwargs)
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                if self.startup_bodies.count(b"\x07") >= 4:
                    probed.set()

        self.client.write_gatt_char.side_effect = probe
        self.bridge.async_process_j1587.side_effect = None
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ):
            task = asyncio.create_task(self.receiver.async_run())
            try:
                await asyncio.wait_for(probed.wait(), 2)
                async with asyncio.timeout(1):
                    while (
                        self.bridge.async_process_j1587.await_count < 4
                        or self.receiver._startup.keepalive_responses < 3
                    ):
                        await asyncio.sleep(0)
                self.assertTrue(self.receiver._startup.ready)
                self.assertEqual(self.startup_bodies.count(b"\x00"), 1)
                self.assertEqual(self.startup_bodies.count(b"\x82\x00"), 1)
                self.assertEqual(self.startup_bodies.count(b"\x99\x01"), 1)
                self.assertGreaterEqual(
                    self.receiver._startup.keepalive_responses, 3
                )
            finally:
                self.receiver.stop()
                await asyncio.wait_for(task, 1)
        sent = self.client.write_gatt_char.await_count
        await asyncio.sleep(0.02)
        self.assertEqual(self.client.write_gatt_char.await_count, sent)
        self.assertIsNone(self.receiver._startup._response)

    async def test_keepalive_timeout_is_recorded_and_disconnects(self):
        self.configure_startup_session(report_on_start=False)
        write = self.client.write_gatt_char.side_effect

        async def ignore_probe(*args, **kwargs):
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                return
            await write(*args, **kwargs)

        self.client.write_gatt_char.side_effect = ignore_probe
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ), patch(
            "custom_components.bluefire.startup.STEP_TIMEOUT", 0.2
        ), patch.object(
            self.receiver, "_receive_is_recent", return_value=False,
        ):
            with self.assertRaisesRegex(
                self.home_assistant_error, "Timed out during J1708 keepalive"
            ):
                await asyncio.wait_for(
                    self.receiver._async_receive_session(), 2
                )
        self.assertEqual(self.receiver._startup.stage, "failed")
        self.client.disconnect.assert_awaited_once()
        self.assertFalse(self.receiver.connection_diagnostics()["connected"])

    async def test_missing_probe_replies_keep_receiving_session_open(self):
        self.configure_startup_session(report_on_start=False)
        write = self.client.write_gatt_char.side_effect
        ignore = True

        async def probe(*args, **kwargs):
            if (
                ignore and args[1][2:-1] == b"\x07"
                and self.receiver._startup.ready
            ):
                self.receiver._notification_received(
                    None, self.packet(b"\xff")
                )
                return
            await write(*args, **kwargs)

        self.client.write_gatt_char.side_effect = probe
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ), patch(
            "custom_components.bluefire.startup.STEP_TIMEOUT", 0.2
        ):
            task = asyncio.create_task(self.receiver.async_run())
            try:
                async with asyncio.timeout(2):
                    while (
                        self.receiver._startup is None
                        or self.receiver._startup.keepalive_timeouts < 3
                    ):
                        await asyncio.sleep(0.01)
                self.assertFalse(task.done())
                self.assertTrue(self.receiver._connected)
                self.client.disconnect.assert_not_awaited()
                self.assertEqual(self.connect.await_count, 1)
                ignore = False
                async with asyncio.timeout(1):
                    while not self.receiver._startup.keepalive_responses:
                        await asyncio.sleep(0.01)
                self.assertEqual(
                    self.receiver._startup.keepalive_consecutive_timeouts, 0
                )
            finally:
                self.receiver.stop()
                await asyncio.wait_for(task, 1)

    async def test_probe_write_failure_reaches_health_and_offline_state(self):
        self.configure_startup_session(report_on_start=False)
        write = self.client.write_gatt_char.side_effect

        async def fail_probe(*args, **kwargs):
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                raise self.bleak_error("probe write failed")
            await write(*args, **kwargs)

        self.client.write_gatt_char.side_effect = fail_probe
        self.receiver.health.add_listener(self.receiver.stop)
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ):
            await asyncio.wait_for(self.receiver.async_run(), 2)
        self.assertEqual(self.receiver.health.counters["connection_errors"], 1)
        self.assertIn("probe write failed", self.receiver.health.last_error)
        self.assertEqual(self.receiver._startup.stage, "failed")
        self.assertEqual(self.receiver._startup.error, "probe write failed")
        self.bridge.async_disconnected.assert_awaited_once()
        self.client.disconnect.assert_awaited_once()

    async def test_probe_sends_independently_of_mqtt_publication(self):
        self.configure_startup_session()
        publishing = asyncio.Event()
        release = asyncio.Event()
        probed = asyncio.Event()
        write = self.client.write_gatt_char.side_effect

        async def publish(_report):
            publishing.set()
            await release.wait()

        async def probe(*args, **kwargs):
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                self.startup_bodies.append(b"\x07")
                reply = self.packet(b"\x07\x01")
                for fragment in (reply[:2], reply[2:4], reply[4:]):
                    self.receiver._notification_received(None, fragment)
                probed.set()
            else:
                await write(*args, **kwargs)

        self.bridge.async_process_j1587.side_effect = publish
        self.client.write_gatt_char.side_effect = probe
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ), patch(
            "custom_components.bluefire.startup.STEP_TIMEOUT", 0.05
        ):
            task = asyncio.create_task(self.receiver.async_run())
            try:
                await asyncio.wait_for(publishing.wait(), 1)
                await asyncio.wait_for(probed.wait(), 1)
                await asyncio.sleep(0.1)
                self.assertFalse(release.is_set())
                self.assertTrue(self.receiver._startup.ready)
                self.assertGreaterEqual(
                    self.receiver._startup.keepalive_responses, 3
                )
                release.set()
                async with asyncio.timeout(1):
                    while not self.receiver._startup.keepalive_responses:
                        await asyncio.sleep(0)
            finally:
                release.set()
                self.receiver.stop()
                await asyncio.wait_for(task, 1)

    async def test_pause_cancels_pending_probe_before_releasing_ble(self):
        self.configure_startup_session(report_on_start=False)
        waiting = asyncio.Event()
        write = self.client.write_gatt_char.side_effect

        async def ignore_probe(*args, **kwargs):
            if args[1][2:-1] == b"\x07" and self.receiver._startup.ready:
                waiting.set()
                return
            await write(*args, **kwargs)

        self.client.write_gatt_char.side_effect = ignore_probe
        with patch(
            "custom_components.bluefire.startup.KEEPALIVE_INTERVAL", 0.01
        ):
            task = asyncio.create_task(self.receiver.async_run())
            try:
                await asyncio.wait_for(waiting.wait(), 1)
                await self.receiver.async_pause()
                self.assertIsNone(self.receiver._startup._response)
                sent = self.client.write_gatt_char.await_count
                await asyncio.sleep(0.03)
                self.assertEqual(self.client.write_gatt_char.await_count, sent)
                self.client.disconnect.assert_awaited_once()
                self.bridge.async_disconnected.assert_not_awaited()
                history = self.receiver.connection_diagnostics()[
                    "connection_history"
                ]
                self.assertEqual(history[-1]["end_event"], "paused")
                self.assertEqual(
                    history[-1]["reason"], "Diagnostic inspection requested"
                )
                context = history[-1]["context"]
                self.assertEqual(context["startup"]["stage"], "ready")
                self.assertEqual(context["startup"]["expected_command"], 7)
                self.assertEqual(context["startup"]["keepalive"]["requests"],
                                 1)
                self.assertEqual(context["last_write"]["command"], 7)
                self.assertIsNotNone(history[-1]["ready_at"])
            finally:
                self.receiver.stop()
                await asyncio.wait_for(task, 1)

    async def test_live_capture_keeps_session_open_and_counts_once(self):
        self.configure_startup_session(report_on_start=False)
        task = asyncio.create_task(self.receiver._async_receive_session())
        capture = None
        try:
            async with asyncio.timeout(1):
                while not (
                    self.receiver._startup and self.receiver._startup.ready
                ):
                    await asyncio.sleep(0)
            before = dict(self.receiver.health.counters)
            capture = asyncio.create_task(self.receiver.async_capture(0.03))
            await asyncio.sleep(0)
            characteristic = SimpleNamespace(
                uuid=self.api.EZ_RECEIVE, handle=16
            )
            self.receiver._notification_received(
                characteristic, self.packet(b"\xff")
            )
            result = await capture
            self.assertEqual(result["mode"], "live")
            self.assertFalse(result["connection_lost"])
            self.assertEqual(result["received_notifications"], 1)
            self.assertEqual(result["notifications"][0]["handle"], 16)
            self.assertEqual(result["notifications"][0]["hex"],
                             self.packet(b"\xff").hex())
            self.assertEqual(self.receiver.health.counters["notifications"],
                             before["notifications"] + 1)
            self.assertEqual(self.receiver.health.counters["heartbeats"],
                             before["heartbeats"] + 1)
            self.assertEqual(self.receiver.health.counters["captures"], 1)
            self.client.disconnect.assert_not_awaited()
            self.assertFalse(task.done())
        finally:
            if capture is not None and not capture.done():
                capture.cancel()
                await asyncio.gather(capture, return_exceptions=True)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_live_capture_is_bounded_and_stops_at_session_boundary(self):
        self.receiver._connected = True
        self.receiver._session_ended = asyncio.Event()
        with patch.object(self.api, "MAX_CAPTURE_NOTIFICATIONS", 1):
            task = asyncio.create_task(self.receiver.async_capture(20))
            await asyncio.sleep(0)
            with self.assertRaisesRegex(
                self.home_assistant_error, "already running"
            ):
                await self.receiver.async_capture(0)
            for _ in range(3):
                self.receiver._notification_received(
                    None, self.packet(b"\xff")
                )
            self.receiver._session_ended.set()
            result = await asyncio.wait_for(task, 1)
        self.assertTrue(result["connection_lost"])
        self.assertEqual(result["received_notifications"], 3)
        self.assertEqual(result["dropped_notifications"], 2)
        self.assertEqual(len(result["notifications"]), 1)
        self.assertEqual(self.receiver.health.counters["notifications"], 3)
        self.assertIsNone(self.receiver._capture_callback)

    async def test_live_capture_skips_offline_and_cleans_up_on_cancel(self):
        result = await self.receiver.async_capture(20)
        self.assertEqual(result["status"], "skipped")
        self.connect.assert_not_awaited()
        self.receiver._connected = True
        self.receiver._session_ended = asyncio.Event()
        task = asyncio.create_task(self.receiver.async_capture(20))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.receiver._capture_callback)
        self.assertEqual(self.receiver.health.counters["captures"], 0)

    async def test_failed_write_aborts_startup_and_disconnects(self):
        self.configure_startup_session()
        self.client.write_gatt_char.side_effect = self.bleak_error(
            "write refused"
        )
        with self.assertRaisesRegex(self.bleak_error, "write refused"):
            await asyncio.wait_for(
                self.receiver._async_receive_session(), 2
            )
        self.client.disconnect.assert_awaited_once()
        self.assertIsNone(self.receiver._startup._response)
        self.assertEqual(
            self.receiver.startup_diagnostics()["error"], "write refused"
        )
        self.assertEqual(
            self.receiver.startup_diagnostics()["stage"], "failed"
        )
        self.bridge.async_process_j1587.assert_not_awaited()

    async def test_pause_cancels_active_startup_and_resumes_a_fresh_session(
        self,
    ):
        self.configure_startup_session(overrides={0: None})
        writing = asyncio.Event()
        write = self.client.write_gatt_char.side_effect

        async def signal_write(*args, **kwargs):
            await write(*args, **kwargs)
            writing.set()

        self.client.write_gatt_char.side_effect = signal_write
        task = asyncio.create_task(self.receiver.async_run())
        await asyncio.wait_for(writing.wait(), 1)
        await self.receiver.async_pause()
        self.client.disconnect.assert_awaited_once()
        self.assertIsNone(self.receiver._startup._response)
        self.bridge.async_disconnected.assert_not_awaited()
        self.receiver.async_resume()
        self.receiver.stop()
        await asyncio.wait_for(task, 1)

    async def test_startup_requires_format_and_both_ez_characteristics(self):
        self.configure_startup_session()
        self.receiver.j1587_extended = None
        with self.assertRaisesRegex(
            self.home_assistant_error, "Select a J1587"
        ):
            await self.receiver._async_receive_session()
        self.receiver.j1587_extended = True
        self.write_characteristic.properties = ["write-without-response"]
        with self.assertRaisesRegex(
            self.home_assistant_error, "requires both EZ"
        ):
            await self.receiver._async_receive_session()
        self.client.write_gatt_char.assert_not_awaited()

    def test_disabled_and_not_started_diagnostics(self):
        self.assertEqual(
            self.receiver.startup_diagnostics(), {"stage": "disabled"}
        )
        self.receiver.j1708_startup = True
        self.assertEqual(
            self.receiver.startup_diagnostics(), {"stage": "not_started"}
        )


if __name__ == "__main__":
    unittest.main()
