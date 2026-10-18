"""Exercise the provisional BLE receiver without a radio or broker."""

import importlib
import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.health import Health


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
