"""Exercise the provisional BLE receiver without a radio or broker."""

import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


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
        self.home_assistant_error = type("HomeAssistantError", (Exception,), {})
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
            object(), "AA:BB:CC:DD:EE:01", self.bridge
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
            await self.receiver._async_process_body(
                self.api.parse_message(message)
            )
        self.bridge.async_process_pgn_report.assert_awaited_once()
        report = self.bridge.async_process_pgn_report.await_args.args[0]
        self.assertEqual(report.pgn, 61444)
        self.assertEqual(report.data, bytes.fromhex("00 00 7d 40 1f ff ff ff"))

    async def test_configured_j1587_format_and_obd_reports_route_separately(self):
        self.receiver.j1587_extended = True
        await self.receiver._async_process_body(
            self.api.parse_message(
                bytes.fromhex("9a 80 be 02 34 12"),
                j1587_extended=True,
            )
        )
        self.bridge.async_process_j1587.assert_awaited_once()
        self.assertEqual(
            self.bridge.async_process_j1587.await_args.args[0].pid, 190
        )
        await self.receiver._async_process_body(
            self.api.parse_message(
                bytes.fromhex("ae 07 e8 01 00 0c 02 1f 40")
            )
        )
        self.bridge.async_process_obd_report.assert_awaited_once()
        self.assertEqual(
            self.bridge.async_process_obd_report.await_args.args[0].pid, 12
        )

    async def test_j1587_is_ignored_until_firmware_format_is_explicit(self):
        await self.receiver._async_process_body(
            bytes.fromhex("9a 80 be 02 34 12")
        )
        self.bridge.async_process_j1587.assert_not_awaited()

    async def test_controls_and_heartbeats_never_mark_telemetry_online(self):
        for command in (255, 42):
            await self.receiver._async_process_body(bytes((command,)))
        self.bridge.async_process_pgn_report.assert_not_awaited()
        self.bridge.async_process_j1587.assert_not_awaited()
        self.bridge.async_process_obd_report.assert_not_awaited()

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


if __name__ == "__main__":
    unittest.main()
