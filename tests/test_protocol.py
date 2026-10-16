"""Synthetic behavioral vectors, not vendor code or captured vehicle data."""

import random
import unittest

from custom_components.bluefire.protocol import (
    AdapterMessage,
    J1587Report,
    MAX_BODY_SIZE,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
    receive_checksum,
)
from custom_components.bluefire.telemetry import SIGNALS


HEARTBEAT = bytes.fromhex("00 01 01 ff 00")
RPM_PACKET = bytes.fromhex(
    "00 0f 0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88"
)
RPM_BODY = RPM_PACKET[3:-1]


def packet(body):
    """Independent test oracle using one's-complement sum modulo 255."""
    total = sum(body)
    checksum = 255 if total == 0 else 255 - ((total - 1) % 255 + 1)
    high, low = divmod(len(body), 256)
    return bytes((high, low, high ^ low)) + body + bytes((checksum,))


class ReceiveTests(unittest.TestCase):
    def test_fixed_vectors_and_checksum_carry(self):
        self.assertEqual(
            ReceiveDecoder().feed(RPM_PACKET + HEARTBEAT),
            (RPM_BODY, b"\xff"),
        )
        for body, expected in (
            (b"\x00", 255), (b"\xff", 0),
            (b"\xff\x01", 254), (b"\xff\xff", 0),
            (bytes([255]) * 260, 0), (RPM_BODY, 0x88),
        ):
            with self.subTest(body=body):
                self.assertEqual(receive_checksum(body), expected)
                self.assertEqual(ReceiveDecoder().feed(packet(body)), (body,))

    def test_every_two_chunk_split(self):
        for padded in (False, True):
            for split in range(len(RPM_PACKET) + 1):
                with self.subTest(padded=padded, split=split):
                    decoder = ReceiveDecoder(padded_notifications=padded)
                    bodies = decoder.feed(RPM_PACKET[:split])
                    bodies += decoder.feed(RPM_PACKET[split:])
                    self.assertEqual(bodies, (RPM_BODY,))
                    self.assertEqual(decoder.pending_bytes, 0)
                    decoder.finish()

    def test_one_byte_chunks_and_coalesced_packets(self):
        decoder = ReceiveDecoder()
        result = ()
        for value in RPM_PACKET + HEARTBEAT + RPM_PACKET:
            result += decoder.feed(bytes((value,)))
        self.assertEqual(result, (RPM_BODY, b"\xff", RPM_BODY))
        self.assertEqual(
            decoder.feed(HEARTBEAT * 1000), (b"\xff",) * 1000
        )

    def test_partial_second_packet_is_preserved(self):
        decoder = ReceiveDecoder()
        self.assertEqual(
            decoder.feed(HEARTBEAT + RPM_PACKET[:10]), (b"\xff",)
        )
        self.assertEqual(decoder.pending_bytes, 10)
        self.assertEqual(decoder.feed(RPM_PACKET[10:]), (RPM_BODY,))

    def test_notification_padding_is_not_another_header(self):
        decoder = ReceiveDecoder(padded_notifications=True)
        self.assertEqual(
            decoder.feed(RPM_PACKET + bytes(5)), (RPM_BODY,)
        )
        self.assertEqual(decoder.feed(HEARTBEAT + bytes(11)), (b"\xff",))
        self.assertEqual(decoder.pending_bytes, 0)
        for tail in (b"\x01", HEARTBEAT, bytes(3) + b"\x01"):
            with self.subTest(tail=tail), self.assertRaises(ProtocolError):
                decoder.feed(RPM_PACKET + tail)
            self.assertEqual(decoder.pending_bytes, 0)
        with self.assertRaises(ProtocolError):
            ReceiveDecoder().feed(RPM_PACKET + bytes(5))

    def test_invalid_headers_and_lengths_fail_without_resync(self):
        for bad in (
            b"\x00\x00\x00",
            b"\x00\x01\x00",
            b"\xff\xff\x00",
            b"\x01\x05\x04",
            b"\x01\x01\xff",
        ):
            decoder = ReceiveDecoder()
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                decoder.feed(bad + HEARTBEAT)
            self.assertEqual(decoder.pending_bytes, 0)
            self.assertEqual(decoder.feed(HEARTBEAT), (b"\xff",))

    def test_corrupt_payload_or_checksum_is_rejected(self):
        for index in range(3, len(RPM_PACKET)):
            bad = bytearray(RPM_PACKET)
            bad[index] ^= 1
            decoder = ReceiveDecoder()
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                decoder.feed(bytes(bad))
            self.assertEqual(decoder.pending_bytes, 0)
        # No partial success from a feed that also contains a corrupt packet.
        with self.assertRaises(ProtocolError):
            ReceiveDecoder().feed(HEARTBEAT + bytes(bad))

    def test_limit_and_big_endian_length(self):
        for length in (1, 255, 256, MAX_BODY_SIZE):
            body = bytes(index % 256 for index in range(length))
            decoder = ReceiveDecoder()
            encoded = packet(body)
            for value in encoded[:-1]:
                self.assertEqual(decoder.feed(bytes((value,))), ())
                self.assertLess(decoder.pending_bytes, 264)
            self.assertEqual(decoder.feed(encoded[-1:]), (body,))

    def test_truncation_and_disconnect_clear_fragments(self):
        for split in range(1, len(RPM_PACKET)):
            decoder = ReceiveDecoder()
            self.assertEqual(decoder.feed(RPM_PACKET[:split]), ())
            self.assertEqual(decoder.feed(b""), ())
            with self.assertRaisesRegex(ProtocolError, "incomplete"):
                decoder.finish()
            self.assertEqual(decoder.pending_bytes, 0)
            self.assertEqual(decoder.feed(HEARTBEAT), (b"\xff",))
            decoder.feed(RPM_PACKET[:split])
            decoder.reset()
            self.assertEqual(decoder.feed(HEARTBEAT), (b"\xff",))

    def test_invalid_types_clear_pending_data(self):
        decoder = ReceiveDecoder()
        for value in (None, bytearray(3), "000101ff00"):
            decoder.feed(RPM_PACKET[:2])
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                decoder.feed(value)
            self.assertEqual(decoder.pending_bytes, 0)

    def test_deterministic_randomized_fragmentation(self):
        rng = random.Random(975)
        bodies = [
            bytes(rng.randrange(256) for _ in range(rng.randint(1, 260)))
            for _ in range(200)
        ]
        stream = b"".join(packet(body) for body in bodies)
        decoder = ReceiveDecoder()
        decoded = []
        offset = 0
        while offset < len(stream):
            size = rng.randint(1, 400)
            decoded.extend(decoder.feed(stream[offset:offset + size]))
            self.assertLess(decoder.pending_bytes, 264)
            offset += size
        decoder.finish()
        self.assertEqual(decoded, bodies)


class ReportTests(unittest.TestCase):
    def test_pgn_metadata_and_can_payload_have_different_byte_orders(self):
        report = parse_message(RPM_BODY)
        self.assertEqual(
            report, PgnReport(
                0, 61444, 6, 0, bytes.fromhex("ff ff 7d 40 1f ff ff ff")
            ),
        )
        rpm = next(signal for signal in SIGNALS if signal.spn == 190)
        self.assertEqual(rpm.decode(report.data), 1000)
        self.assertFalse(hasattr(report, "can_id"))

    def test_pgn_metadata_is_preserved_without_pdu1_guessing(self):
        report = parse_message(bytes.fromhex("97 03 ec ff 06 01 01 20"))
        self.assertEqual(report.pgn, 0xECFF)
        self.assertEqual(report.source_address, 3)
        self.assertEqual(report.data_page, 1)
        self.assertEqual(report.data, b"\x20")
        self.assertFalse(hasattr(report, "can_id"))

    def test_zero_short_and_long_reports_are_not_padded_into_can_frames(self):
        for length in (0, 1, 7, 8, 9, 253):
            body = bytes((151, 3, 0xFE, 0xCA, 6, 0, length)) + bytes(length)
            self.assertEqual(parse_message(body).data, bytes(length))

    def test_legacy_and_extended_j1587_are_explicit(self):
        legacy = bytes.fromhex("9a 80 01 00 02 12 34")
        self.assertEqual(
            parse_message(legacy, j1587_extended=False),
            J1587Report(128, 256, b"\x12\x34"),
        )
        for pages in range(4):
            body = bytes((154, 128)) + b"\xff" * pages
            body += bytes.fromhex("be 02 34 12")
            self.assertEqual(
                parse_message(body, j1587_extended=True),
                J1587Report(128, pages * 256 + 190, b"\x34\x12"),
            )
        with self.assertRaisesRegex(ProtocolError, "explicitly"):
            parse_message(legacy)
        # These formats can be ambiguous; never select one by trial parsing.
        ambiguous = bytes.fromhex("9a 80 01 03 02 12 34")
        self.assertNotEqual(
            parse_message(ambiguous, j1587_extended=False),
            parse_message(ambiguous, j1587_extended=True),
        )

    def test_obd_is_not_j1939(self):
        body = bytes.fromhex("ae 07 e8 01 00 0c 02 1f 40")
        self.assertEqual(
            parse_message(body), ObdReport(0x7E8, 1, 12, b"\x1f\x40")
        )

    def test_controls_unknowns_and_heartbeat_remain_messages(self):
        for body in (b"\xff", b"\x81", b"\x01\x01", b"\x42\x12\x34"):
            self.assertEqual(
                parse_message(body), AdapterMessage(body[0], body[1:])
            )

    def test_truncated_headers_and_inexact_lengths_are_rejected(self):
        examples = (
            (RPM_BODY, {}),
            (bytes.fromhex("9a 80 00 be 02 12 34"),
             {"j1587_extended": False}),
            (bytes.fromhex("9a 80 ff be 02 12 34"),
             {"j1587_extended": True}),
            (bytes.fromhex("ae 07 e8 01 00 0c 02 1f 40"), {}),
        )
        for body, options in examples:
            for length in range(1, len(body)):
                with self.subTest(body=body, length=length):
                    with self.assertRaises(ProtocolError):
                        parse_message(body[:length], **options)
            with self.assertRaises(ProtocolError):
                parse_message(body + b"\x00", **options)

    def test_invalid_pid_extensions_and_legacy_range(self):
        for body in (
            bytes.fromhex("9a 80 ff ff ff ff 01 00"),
            bytes.fromhex("9a 80 ff"),
            bytes.fromhex("9a 80 ff ff ff"),
        ):
            with self.subTest(body=body), self.assertRaises(ProtocolError):
                parse_message(body, j1587_extended=True)
        with self.assertRaises(ProtocolError):
            parse_message(
                bytes.fromhex("9a 80 04 00 00"), j1587_extended=False
            )

    def test_invalid_body_types_and_sizes(self):
        for body in (None, "", b"", bytearray(8), bytes(MAX_BODY_SIZE + 1)):
            with self.subTest(body=body), self.assertRaises(ProtocolError):
                parse_message(body)


if __name__ == "__main__":
    unittest.main()
