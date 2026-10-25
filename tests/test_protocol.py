"""Synthetic behavioral vectors, not vendor code or captured vehicle data."""

import random
import unittest

from custom_components.bluefire.protocol import (
    AdapterMessage,
    J1587Report,
    MAX_BODY_SIZE,
    MAX_PACKET_SIZE,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    RecoveringReceiveDecoder,
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

    def test_modern_stream_keeps_tails_after_completing_a_fragment(self):
        decoder = ReceiveDecoder()
        self.assertEqual(decoder.feed(RPM_PACKET[:4]), ())
        self.assertEqual(
            decoder.feed(RPM_PACKET[4:] + HEARTBEAT + RPM_PACKET[:2]),
            (RPM_BODY, b"\xff"),
        )
        self.assertEqual(decoder.pending_bytes, 2)
        self.assertEqual(decoder.feed(RPM_PACKET[2:]), (RPM_BODY,))
        decoder.finish()

    def test_pgn_header_pattern_is_not_a_synchronization_marker(self):
        nested = b"\x42" + RPM_PACKET + b"\x00"
        self.assertEqual(ReceiveDecoder().feed(packet(nested)), (nested,))
        for corrupt in (
            b"\x42" + RPM_PACKET,
            packet(nested)[:-1] + b"\x00" + RPM_PACKET,
            b"\x00\x0f\x0f\x97" + bytes(15) + RPM_PACKET,
        ):
            decoder = ReceiveDecoder()
            with self.subTest(corrupt=corrupt):
                with self.assertRaises(ProtocolError):
                    decoder.feed(corrupt)
                self.assertEqual(decoder.pending_bytes, 0)
                self.assertEqual(decoder.feed(HEARTBEAT), (b"\xff",))

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


class RecoveryTests(unittest.TestCase):
    def test_valid_streams_and_nested_headers_are_unchanged(self):
        nested = b"\x42" + HEARTBEAT * 2 + b"\x00"
        stream = packet(nested) + RPM_PACKET + HEARTBEAT
        for split in range(len(stream) + 1):
            decoder = RecoveringReceiveDecoder()
            bodies = decoder.feed(stream[:split])
            bodies += decoder.feed(stream[split:])
            self.assertEqual(bodies, (nested, RPM_BODY, b"\xff"))
            self.assertEqual(decoder.resynchronizations, 0)
            self.assertEqual(decoder.framing_errors, ())

    def test_missing_body_preserves_good_prefix_and_recovers_good_tail(self):
        reports = [
            bytes((154, 128, 190, 2, value, 0)) for value in range(15)
        ]
        stream = packet(reports[0]) + b"\x00\x05\x05"
        stream += b"".join(packet(body) for body in reports[1:])
        for split in range(len(stream) + 1):
            decoder = RecoveringReceiveDecoder()
            bodies = decoder.feed(stream[:split])
            errors = decoder.framing_errors
            bodies += decoder.feed(stream[split:])
            errors += decoder.framing_errors
            self.assertEqual(bodies, tuple(reports))
            self.assertEqual(errors, ("Invalid receive payload checksum",))
            self.assertEqual(decoder.resynchronizations, 1)
            self.assertFalse(decoder.resynchronizing)
            self.assertEqual(decoder.pending_bytes, 0)

    def test_recovery_requires_two_adjacent_complete_valid_packets(self):
        decoder = RecoveringReceiveDecoder()
        self.assertEqual(decoder.feed(b"\x7f\x00\x00" + HEARTBEAT), ())
        self.assertTrue(decoder.resynchronizing)
        self.assertEqual(decoder.feed(RPM_PACKET[:-1]), ())
        self.assertEqual(decoder.feed(RPM_PACKET[-1:]),
                         (b"\xff", RPM_BODY))
        self.assertEqual(decoder.resynchronizations, 1)

    def test_incomplete_false_header_cannot_block_a_later_valid_pair(self):
        decoder = RecoveringReceiveDecoder()
        self.assertEqual(
            decoder.feed(b"\x7f\x00\x00\x01\x04\x05" + HEARTBEAT * 2),
            (b"\xff", b"\xff"),
        )
        self.assertFalse(decoder.resynchronizing)

    def test_corrupt_candidate_is_never_returned_during_recovery(self):
        bad = RPM_PACKET[:-1] + bytes((RPM_PACKET[-1] ^ 1,))
        decoder = RecoveringReceiveDecoder()
        self.assertEqual(decoder.feed(bad + HEARTBEAT + bad), ())
        self.assertEqual(decoder.feed(HEARTBEAT * 2), (b"\xff", b"\xff"))
        self.assertEqual(decoder.resynchronizations, 1)

    def test_noise_is_bounded_and_two_maximum_packets_can_recover(self):
        decoder = RecoveringReceiveDecoder()
        for _ in range(20):
            self.assertEqual(decoder.feed(bytes(1000)), ())
            self.assertLessEqual(decoder.pending_bytes, MAX_PACKET_SIZE * 2)
        bodies = (bytes([42]) * MAX_BODY_SIZE, bytes([43]) * MAX_BODY_SIZE)
        stream = b"".join(packet(body) for body in bodies)
        for value in stream[:-1]:
            self.assertEqual(decoder.feed(bytes((value,))), ())
            self.assertLessEqual(decoder.pending_bytes, MAX_PACKET_SIZE * 2)
        self.assertEqual(decoder.feed(stream[-1:]), bodies)
        self.assertEqual(decoder.pending_bytes, 0)

    def test_multiple_errors_in_one_feed_keep_all_valid_packets(self):
        decoder = RecoveringReceiveDecoder()
        noise = b"\x7f\x00\x00"
        self.assertEqual(
            decoder.feed(HEARTBEAT + (noise + HEARTBEAT * 2) * 2),
            (b"\xff",) * 5,
        )
        self.assertEqual(len(decoder.framing_errors), 2)
        self.assertEqual(decoder.resynchronizations, 2)

    def test_reset_and_invalid_api_input_clear_recovery(self):
        decoder = RecoveringReceiveDecoder()
        for value in (None, bytearray(3), "invalid"):
            decoder.feed(b"\x7f\x00\x00" + HEARTBEAT)
            with self.assertRaises(ProtocolError):
                decoder.feed(value)
            self.assertFalse(decoder.resynchronizing)
            self.assertEqual(decoder.pending_bytes, 0)
        decoder.feed(b"\x7f\x00\x00" + HEARTBEAT)
        decoder.reset()
        self.assertEqual(decoder.feed(HEARTBEAT), (b"\xff",))
        self.assertEqual(decoder.resynchronizations, 0)

    def test_randomized_valid_fragmentation_matches_strict_decoder(self):
        rng = random.Random(323)
        bodies = [
            bytes(rng.randrange(256) for _ in range(rng.randint(1, 260)))
            for _ in range(200)
        ]
        stream = b"".join(packet(body) for body in bodies)
        decoder = RecoveringReceiveDecoder()
        decoded = []
        offset = 0
        while offset < len(stream):
            size = rng.randint(1, 700)
            decoded.extend(decoder.feed(stream[offset:offset + size]))
            self.assertLessEqual(decoder.pending_bytes, MAX_PACKET_SIZE * 2)
            offset += size
        self.assertEqual(decoded, bodies)
        self.assertEqual(decoder.resynchronizations, 0)


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

    def test_component_mid_wrapper_is_normalized_only_at_vendor_boundary(self):
        for extended in (False, True):
            pid = b"\xf3" if extended else b"\x00\xf3"
            for mid in (128, 130, 249):
                data = bytes((mid,)) + b"MAKE*MODEL*SERIAL*"
                body = bytes((154, mid)) + pid + bytes((len(data),)) + data
                self.assertEqual(
                    parse_message(body, j1587_extended=extended),
                    J1587Report(mid, 243, data[1:]),
                )
                with self.assertRaisesRegex(ProtocolError, "MID mismatch"):
                    parse_message(
                        bytes((154, mid + 1)) + body[2:],
                        j1587_extended=extended,
                    )
            for data in (b"", b"\xff\xff", b"MAKE*MODEL*"):
                body = b"\x9a\x80" + pid + bytes((len(data),)) + data
                self.assertEqual(
                    parse_message(body, j1587_extended=extended).data, data,
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

    def test_newer_control_commands_are_not_guessed_or_correlated(self):
        commands = (
            0, 9, 10, 128, 129, 130, 131, 168, 169, 171, 177, 178,
            197, 198, 201, 206, 207, 214, 215, 216, 255,
        )
        for command in commands:
            # A telemetry-looking control body must remain opaque.
            body = bytes((command,)) + RPM_PACKET
            decoded, = ReceiveDecoder().feed(packet(body))
            with self.subTest(command=command):
                self.assertEqual(
                    parse_message(decoded), AdapterMessage(command, RPM_PACKET)
                )
        for body in (
            bytes.fromhex("c9 18 f0 04 03"), RPM_BODY, b"\xb1\x12\x34",
            bytes((151, 3)) + RPM_BODY[2:],
        ):
            with self.subTest(body=body):
                report = parse_message(body)
                self.assertFalse(hasattr(report, "can_id"))
                if isinstance(report, PgnReport):
                    self.assertEqual(report.pgn, 61444)
                    self.assertEqual(report.source_address, body[1])

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
