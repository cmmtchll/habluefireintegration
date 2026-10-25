"""Exercise the provisional BLE receiver without a radio or broker."""

import importlib
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.health import Health
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
            (60, 96), (65, 194), (120, 96), (125, 194),
            (180, 96), (185, 194),
        ])
        self.assertEqual(sleeps, [60, 50, 50, 50])

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
        self.assertEqual(
            [time for time, pid in reads if pid == 194],
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
        self.assertEqual(reads, [(120, 96), (120, 194)])

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

    async def test_automatic_poll_sends_reads_and_restores_passive_wire_modes(
        self,
    ):
        self.configure_startup_session()
        self.bridge.async_process_j1587.side_effect = None
        completed = asyncio.Event()
        original_write = self.client.write_gatt_char.side_effect

        async def write(characteristic, packet, *, response):
            await original_write(characteristic, packet, response=response)
            body = packet[2:-1]
            if body == bytes.fromhex("9b 00 00 60 01 01 00 00 00"):
                self.receiver._notification_received(
                    None, self.packet(bytes.fromhex("9a 80 60 01 64"))
                )
            elif body == bytes.fromhex("9b 00 00 c2 01 01 00 00 00"):
                self.receiver._notification_received(
                    None, self.packet(bytes.fromhex("9a 80 c2 00"))
                )
            elif body == bytes.fromhex("9b 00 00 c2 00 02 03 e8 00"):
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
        self.assertEqual(self.startup_bodies[-4:], [
            bytes.fromhex("9b 00 00 60 01 01 00 00 00"),
            bytes.fromhex("9b 00 00 60 00 02 03 e8 00"),
            bytes.fromhex("9b 00 00 c2 01 01 00 00 00"),
            bytes.fromhex("9b 00 00 c2 00 02 03 e8 00"),
        ])
        reports = [
            call.args[0] for call in
            self.bridge.async_process_j1587.await_args_list
        ]
        self.assertTrue(any(
            r.pid == 96 and r.data == b"\x64" for r in reports
        ))
        self.assertTrue(any(r.pid == 194 and r.data == b"" for r in reports))

    def configure_read(self):
        self.receiver.j1708_startup = True
        self.receiver.j1587_extended = True
        self.read_started = asyncio.Event()

        async def read(pid, *, restore=False):
            if not restore:
                self.read_started.set()

        self.receiver._startup = SimpleNamespace(
            ready=True, async_read=AsyncMock(side_effect=read),
            disconnected=Mock(),
        )
        timer = patch.object(self.api, "READ_WINDOW_SECONDS", 0.02)
        timer.start()
        self.addCleanup(timer.stop)

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

    async def test_read_timeout_is_not_an_empty_or_cached_fault_list(self):
        self.configure_read()
        for pid in (96, 194):
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
                self.home_assistant_error, "Only fuel",
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

        async def stop_after_failure(_delay):
            self.receiver.stop()

        with patch(
            "custom_components.bluefire.receiver.asyncio.sleep",
            new=AsyncMock(side_effect=stop_after_failure),
        ):
            await self.receiver.async_run()

        self.assertEqual(self.receiver.health.counters["framing_errors"], 1)

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
            self.assertEqual(diagnostics["subscriptions_sent"], 32)
            self.assertEqual(diagnostics["discarded_reports"], 1)
        self.assertEqual(self.bridge.async_process_j1587.await_count, 2)
        self.assertEqual(self.startup_bodies.count(b"\x00"), 2)
        self.assertEqual(self.startup_bodies.count(b"\x99\x01"), 2)
        self.assertEqual(self.client.disconnect.await_count, 2)
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
        self.assertEqual(diagnostics["subscriptions_sent"], 32)
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
        self.assertEqual(self.receiver._startup.subscriptions_sent, 32)
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
            "custom_components.bluefire.startup.STEP_TIMEOUT", 0.01
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
