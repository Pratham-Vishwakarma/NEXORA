"""Offline regressions for the Wi-Fi sender/logger serial contract."""

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "tel_log_wifi", Path(__file__).resolve().parents[1] / "src" / "tel_log_wifi.py"
)
wifi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wifi
spec.loader.exec_module(wifi)


class SerialReplay:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.timeout = 1
        self.now = 0.0
        self.writes = []

    def readline(self):
        self.now += 0.1
        return next(self.chunks, b"")

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass


class WifiTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        # Keep output capture active without opening a serial port or API connection.
        self.enterContext(contextlib.redirect_stdout(self.output))

    def test_old_and_new_success_records_remain_successful(self):
        for suffix in ("", ",OK"):
            with self.subTest(suffix=suffix):
                packet = wifi.parse_packet_line("PKT,42,16,-65,12.50,1,0,1000" + suffix)
                self.assertTrue(packet.successful)
                self.assertEqual(packet.rtt_ms, 12.5)
                self.assertIsNone(packet.failure_reason)

    def test_failures_preserve_firmware_reason(self):
        for reason in ("SEND_FAILED", "ACK_TIMEOUT", "ACK_REJECTED"):
            with self.subTest(reason=reason):
                packet = wifi.parse_packet_line(f"PKT,42,16,-65,-1.00,0,0,1000,{reason}")
                self.assertFalse(packet.successful)
                self.assertIsNone(packet.rtt_ms)
                self.assertEqual(packet.failure_reason, reason)

    def test_old_failure_does_not_invent_a_cause(self):
        packet = wifi.parse_packet_line("PKT,42,16,-65,-1.00,0,0,1000")
        self.assertFalse(packet.successful)
        self.assertEqual(packet.failure_reason, "UNKNOWN")

    def test_inconsistent_records_are_rejected(self):
        for tail in ("2,0,1000", "1,0,1000,ACK_TIMEOUT", "0,0,1000,OK"):
            with self.subTest(tail=tail):
                self.assertIsNone(wifi.parse_packet_line("PKT,42,16,-65,12.50," + tail))

    def test_config_uses_requested_interval_after_startup(self):
        ser = SerialReplay([b"Wi-Fi connected\n", b"Sender ready\n", b"CONFIG_OK,16,1000,11\n"])
        with patch.object(wifi.time, "monotonic", lambda: ser.now), \
                patch.object(wifi, "PACKET_INTERVAL_MS", 1000), \
                patch.object(wifi, "PAYLOAD_BYTES", 16):
            wifi.configure_esp32(ser)
        self.assertEqual(ser.writes, [b"CONFIG,16,1000\n"])

    def test_fragmented_records_reach_output_and_measurement(self):
        ser = SerialReplay([
            b"PWR,1000,50.0\n",
            b"PKT,1,16,-65,12.50,",
            b"1,0,1000,OK\n",
            b"PKT,2,16,-65,-1.00,0,0,1100,SEND_FAILED\n",
        ])
        with patch.object(wifi.time, "monotonic", lambda: ser.now), \
                patch.object(wifi, "TEST_DURATION_SECONDS", 1), \
                patch.object(wifi, "PAYLOAD_BYTES", 16):
            window = wifi.collect_repetition(ser, 1)
            measurement = wifi.build_measurement(window, 1)
        self.assertEqual(ser.timeout, 1)
        self.assertEqual(len(window.packets), 2)
        self.assertEqual(len(window.power_samples), 1)
        self.assertEqual(measurement["packets_received"], 1)
        self.assertEqual(measurement["packets_sent"], 2)
        self.assertEqual(measurement["packet_loss_pct"], 50.0)
        self.assertEqual(measurement["latency_mean_ms"], 12.5)
        self.assertIn("SEND_FAILED: 1", self.output.getvalue())
        self.assertIn("OK", self.output.getvalue())

    def test_oversize_payload_is_rejected_before_serial_config(self):
        with patch.object(wifi, "PAYLOAD_BYTES", 2048):
            with self.assertRaisesRegex(ValueError, "NetworkUDP buffer"):
                wifi.validate_configuration()


if __name__ == "__main__":
    unittest.main()
