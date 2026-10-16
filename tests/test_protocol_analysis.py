"""Exercise the offline CLI without an adapter or private capture files."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from custom_components.bluefire.protocol import ProtocolError
from custom_components.bluefire.signals import SIGNALS
from scripts.analyze_bluefire import analyze_capture, main


class CaptureAnalysisTests(unittest.TestCase):
    def analyze(self, text, **kwargs):
        return list(analyze_capture(
            StringIO(text), padded_notifications=False, **kwargs
        ))

    def test_fragmented_rpm_and_heartbeat(self):
        records = self.analyze(
            "00 0f\n\n0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88\n"
            "00 01 01 ff 00\n"
        )
        rpm, heartbeat = records
        self.assertEqual(rpm["line"], 3)
        self.assertEqual(rpm["kind"], "pgn_report")
        self.assertFalse(rpm["hardware_verified"])
        self.assertNotIn("can_id", rpm)
        self.assertIn(
            {**SIGNALS[0].metadata(), "value": 1000}, rpm["signals"]
        )
        self.assertEqual(heartbeat["kind"], "adapter_message")
        self.assertNotIn("signals", heartbeat)

    def test_nonzero_page_and_short_payload_are_not_catalog_decoded(self):
        for body in ("97 00 f0 04 06 01 00", "97 00 f0 04 06 00 00"):
            # These fixed packets both have a checksum of 0x6C/0x6D.
            suffix = "6c" if "06 01" in body else "6d"
            record, = self.analyze(f"00 07 07 {body} {suffix}")
            self.assertEqual(record["signals"], [])

    def test_other_protocols_and_unknown_commands(self):
        for packet, kind, options in (
            ("00 06 06 9a 80 01 00 01 12 d0", "j1587_report",
             {"j1587_extended": False}),
            ("00 09 09 ae 07 e8 01 00 0c 02 1f 40 f2", "obd_report", {}),
            ("00 02 02 42 01 bc", "adapter_message", {}),
        ):
            with self.subTest(kind=kind):
                record, = self.analyze(packet, **options)
                self.assertEqual(record["kind"], kind)

    def test_modern_controls_interleaved_with_fragmented_reports(self):
        records = self.analyze(
            "00 01 01 ff 00 00 03 03 83 01 f4 86 00 0f\r\n"
            "0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88 "
            "00 03 03 b1 12 34 08\r\n"
            "00 01 01 d6 29\r\n"
        )
        self.assertEqual(
            [record["command"] for record in records],
            [255, 131, 151, 177, 214],
        )
        for record in records:
            if record["kind"] == "pgn_report":
                self.assertIn(
                    {**SIGNALS[0].metadata(), "value": 1000},
                    record["signals"],
                )
            else:
                self.assertEqual(record["kind"], "adapter_message")
                self.assertNotIn("signals", record)
            self.assertNotIn("can_id", record)

    def test_arb_id_response_does_not_manufacture_report_can_ids(self):
        records = self.analyze(
            "00 05 05 c9 18 f0 04 03 26\n"
            "00 0f 0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88\n"
        )
        self.assertEqual(records[0]["kind"], "adapter_message")
        self.assertEqual(records[0]["command"], 201)
        self.assertEqual(records[1]["kind"], "pgn_report")
        self.assertEqual(records[1]["source_address"], 0)
        for record in records:
            self.assertNotIn("can_id", record)
            self.assertNotIn("arbitration_id", record)

    def test_vendor_adapter_txt_replays_without_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Adapter.txt"
            path.write_bytes(
                b"00 0F 0F 97 00 F0 04 06 00 08 FF FF 7D 40 1F FF FF FF "
                b"88 00 01 \r\n01 FF 00 \r\n"
            )
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(
                    main([str(path), "--transport", "stream"]), 0
                )
            records = [
                json.loads(line) for line in output.getvalue().splitlines()
            ]
            self.assertEqual(
                [record["kind"] for record in records],
                ["pgn_report", "adapter_message"],
            )
            self.assertEqual(
                [record["line"] for record in records], [1, 2]
            )
            self.assertEqual(errors.getvalue(), "")

    def test_errors_have_line_numbers_and_no_capture_contents(self):
        for text in (
            "\nzz\n", "00 00 00\n", "00 01 01 ff 01\n",
            "00 01 01 97 68\n", "0" * 4097,
        ):
            with self.subTest(text=text[:20]):
                with self.assertRaisesRegex(ProtocolError, "Line [12]:"):
                    self.analyze(text)
        with self.assertRaisesRegex(ProtocolError, "incomplete"):
            self.analyze("00 01")

    def test_cli_success_error_and_explicit_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.hex"
            path.write_text("00 01 01 ff 00 00 00\n", encoding="ascii")
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(
                    main([str(path), "--transport", "padded",
                          "--j1587-format", "extended"]), 0
                )
            self.assertEqual(
                json.loads(output.getvalue())["kind"], "adapter_message"
            )
            self.assertEqual(errors.getvalue(), "")
            for content in ("00 01", "not hex", "\u00e9"):
                path.write_text(content, encoding="utf-8")
                with redirect_stderr(errors):
                    self.assertEqual(
                        main([str(path), "--transport", "stream"]), 1
                    )
            path.unlink()
            with redirect_stderr(errors):
                self.assertEqual(
                    main([str(path), "--transport", "stream"]), 1
                )
            with redirect_stderr(errors), self.assertRaises(SystemExit):
                main([str(path)])


if __name__ == "__main__":
    unittest.main()
