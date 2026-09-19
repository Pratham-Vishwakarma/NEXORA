from __future__ import annotations
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import requests
import serial
from serial import SerialException

# ============================================================
#                EXPERIMENT VARIABLES
# ============================================================

# ------------------------------------------------------------
# 1. DISTANCE
# ------------------------------------------------------------
DISTANCE_M = 0.0
# ------------------------------------------------------------
# 2. PAYLOAD SIZE
# IMPORTANT:
# Must match PAYLOAD_SIZE in ESP32 sender firmware.
# ------------------------------------------------------------
PAYLOAD_BYTES = 16
# ------------------------------------------------------------
# 3. PACKET INTERVAL
# IMPORTANT:
# Must match SEND_INTERVAL_MS in ESP32 sender firmware.
# ------------------------------------------------------------
PACKET_INTERVAL_MS = 100
# ------------------------------------------------------------
# 4. ENVIRONMENT
# ------------------------------------------------------------
ENVIRONMENT = "INDOOR"
# ------------------------------------------------------------
# 5. VISIBILITY
# ------------------------------------------------------------
LINE_OF_SIGHT = True
# ------------------------------------------------------------
# 6. OBSTACLE
# ------------------------------------------------------------
OBSTACLE_TYPE = None

TRAFFIC_REQUIREMENT = "TELEMETRY"
TEST_DURATION_SECONDS = 20
# ------------------------------------------------------------
# 9. REPETITIONS
# ------------------------------------------------------------
REPETITIONS = 1
MAX_PAYLOAD_BYTES = 2048
# ============================================================
#                PROTOCOL / DEVICE SETTINGS
# ============================================================
PROTOCOL = "BLUETOOTH"
RADIO_FAMILY = "IEEE802.11"
SOURCE_NODE = "ESP32_A"
DESTINATION_NODE = "ESP32_B"
# ============================================================
#             OTHER CONTROLLED METADATA
# ============================================================
MOBILITY = "STATIC"
INTERFERENCE_LEVEL = "LOW"
QOS_PRIORITY = "NORMAL"
REQUIRED_LATENCY_MS = None
REQUIRED_THROUGHPUT_KBPS = None
RELIABILITY_REQUIREMENT = None
POWER_PRIORITY = "NORMAL"
RANGE_REQUIREMENT_M = None
TX_POWER_DBM = None
# ============================================================
#                  POWER MEASUREMENTS
# ============================================================
BATTERY_VOLTAGE = None
CURRENT_MA = None
# ============================================================
#                PROTOCOL-SPECIFIC VALUES
# ============================================================
# Wi-Fi
WIFI_CHANNEL = None
# BLE
BLE_PHY = None
# Bluetooth Classic
BT_MODE = None
# LoRa
LORA_SF = None
LORA_BW = None
LORA_CR = None
# Cellular
CELLULAR_GENERATION = None
CELL_SIGNAL_DBM = None
# ============================================================
#                  SERIAL CONFIGURATION
# ============================================================
SERIAL_PORT = "COM3"
BAUD_RATE = 115200
# ============================================================
#                    API CONFIGURATION
# ============================================================
API_BASE_URL = "http://100.93.151.73:8000"
MEASUREMENT_ENDPOINT = (f"{API_BASE_URL}/measurements")
HTTP_TIMEOUT_SECONDS = 5

# ============================================================
#                  LOCAL FAILURE BACKUP
# ============================================================
FAILED_FILE = Path(
    "data_feed/errors/failed_measurements.jsonl"
)

# ============================================================
#                  ESP32 CONFIGURATION
# ============================================================
def configure_esp32(
    ser: serial.Serial,
) -> None:

    global WIFI_CHANNEL

    command = (
        f"CONFIG,"
        f"{PAYLOAD_BYTES},"
        f"{PACKET_INTERVAL_MS}\n"
    )

    ser.reset_input_buffer()

    ser.write(
        command.encode("utf-8")
    )

    ser.flush()

    print(
        f"[CONFIG] Sent -> "
        f"payload={PAYLOAD_BYTES} bytes, "
        f"interval={PACKET_INTERVAL_MS} ms"
    )

    timeout_at = (
        time.monotonic() + 5
    )

    while (
        time.monotonic()
        < timeout_at
    ):

        raw = ser.readline()

        if not raw:
            continue

        line = (
            raw.decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )

        if not line:
            continue

        print(
            "[ESP]",
            line
        )

        if line.startswith("CONFIG_OK,"):

            parts = line.split(",")

            if len(parts) != 4:
                continue

            confirmed_payload = int(
                parts[1]
            )

            confirmed_interval = int(
                parts[2]
            )

            wifi_channel = int(
                parts[3]
            )

            if (
                confirmed_payload
                != PAYLOAD_BYTES
            ):
                raise RuntimeError(
                    "ESP32 payload confirmation mismatch"
                )

            if (
                confirmed_interval
                != PACKET_INTERVAL_MS
            ):
                raise RuntimeError(
                    "ESP32 interval confirmation mismatch"
                )

            WIFI_CHANNEL = (
                wifi_channel
            )

            print(
                "[CONFIG] ESP32 configuration confirmed"
            )

            print(
                f"[CONFIG] Wi-Fi channel: "
                f"{WIFI_CHANNEL}"
            )

            return

        if line.startswith(
            "CONFIG_ERROR"
        ):

            raise RuntimeError(
                f"ESP32 rejected configuration: {line}"
            )

    raise RuntimeError(
        "ESP32 did not confirm configuration "
        "within 5 seconds"
    )

# ============================================================
#                   PACKET DATA MODEL
# ============================================================

@dataclass
class PacketTelemetry:
    packet_id: int
    payload_bytes: int

    rssi_dbm: float | None
    rtt_ms: float | None

    successful: bool
    retries: int

    timestamp_ms: int

# ============================================================
#                EXPERIMENT-ID GENERATION
# ============================================================

def normalise_name(value: str) -> str:
    return (
        value
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

def build_experiment_id(
    repetition: int,
) -> str:

    visibility = (
        "los"
        if LINE_OF_SIGHT
        else "nlos"
    )

    obstacle = (
        "none"
        if OBSTACLE_TYPE is None
        else normalise_name(
            OBSTACLE_TYPE
        )
    )

    distance_text = (
        str(DISTANCE_M)
        .replace(".", "p")
    )

    return (
        f"{PROTOCOL.lower()}_"
        f"{normalise_name(ENVIRONMENT)}_"
        f"{visibility}_"
        f"d{distance_text}m_"
        f"p{PAYLOAD_BYTES}b_"
        f"i{PACKET_INTERVAL_MS}ms_"
        f"{normalise_name(TRAFFIC_REQUIREMENT)}_"
        f"{obstacle}_"
        f"t{TEST_DURATION_SECONDS}s_"
        f"rep{repetition:02d}"
    )

# ============================================================
#                    SERIAL PARSER
# ============================================================

def parse_packet_line(
    line: str,
) -> PacketTelemetry | None:

    """
    Expected ESP32 serial format:

    PKT,
    packet_id,
    payload_bytes,
    rssi_dbm,
    rtt_ms,
    successful,
    retries,
    timestamp_ms

    Example:

    PKT,42,128,-63,6.00,1,0,49381
    """

    if not line.startswith("PKT,"):
        return None

    parts = line.split(",")

    if len(parts) != 8:
        print(
            f"[WARN] Expected 8 fields, "
            f"got {len(parts)}: {line}"
        )

        return None

    try:

        packet_id = int(
            parts[1]
        )

        payload_bytes = int(
            parts[2]
        )

        rssi_dbm = float(
            parts[3]
        )

        rtt_value = float(
            parts[4]
        )

        successful = bool(
            int(parts[5])
        )

        retries = int(
            parts[6]
        )

        timestamp_ms = int(
            parts[7]
        )

        return PacketTelemetry(
            packet_id=packet_id,

            payload_bytes=payload_bytes,

            rssi_dbm=rssi_dbm,

            rtt_ms=(
                None
                if rtt_value < 0
                else rtt_value
            ),

            successful=successful,

            retries=retries,

            timestamp_ms=timestamp_ms,
        )

    except ValueError as exc:

        print(
            f"[WARN] Parse error: "
            f"{exc}: {line}"
        )

        return None

# ============================================================
#                 MEASUREMENT WINDOW
# ============================================================

class MeasurementWindow:

    def __init__(self) -> None:

        self.packets: list[
            PacketTelemetry
        ] = []

        self.started_at: float | None = None
        self.finished_at: float | None = None


    def start(self) -> None:

        self.packets.clear()

        self.started_at = (
            time.monotonic()
        )

        self.finished_at = None


    def add(
        self,
        packet: PacketTelemetry,
    ) -> None:

        self.packets.append(
            packet
        )


    def stop(self) -> None:

        self.finished_at = (
            time.monotonic()
        )


    @property
    def elapsed_seconds(
        self,
    ) -> float:

        if self.started_at is None:
            return 0.0

        end_time = (
            self.finished_at
            if self.finished_at
            is not None
            else time.monotonic()
        )

        return max(
            end_time
            - self.started_at,
            0.001,
        )

# ============================================================
#                  STATISTICS HELPERS
# ============================================================

def mean_or_none(
    values: list[float],
) -> float | None:

    if not values:
        return None

    return statistics.fmean(
        values
    )

def calculate_jitter(
    rtts: list[float],
) -> float | None:

    if len(rtts) < 2:
        return None

    differences = [
        abs(
            current
            - previous
        )

        for previous, current
        in zip(
            rtts,
            rtts[1:],
        )
    ]

    return statistics.fmean(
        differences
    )

# ============================================================
#             CONFIGURATION VALIDATION
# ============================================================

def validate_configuration() -> None:

    if DISTANCE_M < 0:
        raise ValueError(
            "DISTANCE_M cannot be negative"
        )

    if PAYLOAD_BYTES <= 0:
        raise ValueError(
            "PAYLOAD_BYTES must be > 0"
        )

    if PACKET_INTERVAL_MS <= 0:
        raise ValueError(
            "PACKET_INTERVAL_MS must be > 0"
        )

    if TEST_DURATION_SECONDS <= 0:
        raise ValueError(
            "TEST_DURATION_SECONDS must be > 0"
        )

    if REPETITIONS < 1:
        raise ValueError(
            "REPETITIONS must be >= 1"
        )

    if ENVIRONMENT not in {
        "INDOOR",
        "OPEN",
    }:
        raise ValueError(
            "ENVIRONMENT must be "
            "'INDOOR' or 'OPEN'"
        )

    if OBSTACLE_TYPE not in {
        None,
        "WALL",
        "PEOPLE",
    }:
        raise ValueError(
            "OBSTACLE_TYPE must be "
            "None, 'WALL', or 'PEOPLE'"
        )

    if TRAFFIC_REQUIREMENT not in {
        "TELEMETRY",
        "INTERACTIVE",
        "BULK",
    }:
        raise ValueError(
            "TRAFFIC_REQUIREMENT must be "
            "'TELEMETRY', 'INTERACTIVE', "
            "or 'BULK'"
        )

# ============================================================
#             ESP32 CONFIGURATION VALIDATION
# ============================================================

def validate_packet_configuration(
    packet: PacketTelemetry,
) -> bool:

    # --------------------------------------------------------
    # Validate Python-side configured payload range
    # --------------------------------------------------------

    if not (
        1
        <= PAYLOAD_BYTES
        <= MAX_PAYLOAD_BYTES
    ):

        print()
        print(
            "[INVALID PYTHON CONFIGURATION]"
        )

        print(
            f"PAYLOAD_BYTES must be between "
            f"1 and {MAX_PAYLOAD_BYTES}"
        )

        print(
            f"Current PAYLOAD_BYTES : "
            f"{PAYLOAD_BYTES}"
        )

        print()

        return False


    # --------------------------------------------------------
    # Validate ESP32 actual payload against Python configuration
    # --------------------------------------------------------

    if (
        packet.payload_bytes
        != PAYLOAD_BYTES
    ):

        print()
        print(
            "[CONFIGURATION MISMATCH]"
        )

        print(
            f"Python PAYLOAD_BYTES : "
            f"{PAYLOAD_BYTES}"
        )

        print(
            f"ESP32 payload        : "
            f"{packet.payload_bytes}"
        )

        print(
            "The measurement will NOT "
            "be added to the experiment."
        )

        print()

        return False


    # --------------------------------------------------------
    # Everything matches
    # --------------------------------------------------------

    return True

# ============================================================
#          BUILD MeasurementIn DATABASE PAYLOAD
# ============================================================

def build_measurement(
    window: MeasurementWindow,
    repetition: int,
) -> dict:

    packets = (
        window.packets
    )

    if not packets:
        raise ValueError(
            "No packets collected"
        )


    # --------------------------------------------------------
    # Validate actual payload sizes from ESP32
    # --------------------------------------------------------

    actual_payload_sizes = {
        packet.payload_bytes
        for packet in packets
    }

    if len(
        actual_payload_sizes
    ) != 1:

        raise ValueError(
            "Mixed payload sizes detected "
            "inside the same experiment: "
            f"{actual_payload_sizes}"
        )

    actual_payload_bytes = (
        next(
            iter(
                actual_payload_sizes
            )
        )
    )


    if (
        actual_payload_bytes
        != PAYLOAD_BYTES
    ):

        raise ValueError(
            f"Python configured "
            f"{PAYLOAD_BYTES} B, "
            f"but ESP32 transmitted "
            f"{actual_payload_bytes} B"
        )


    # --------------------------------------------------------
    # Packet counts
    # --------------------------------------------------------

    packets_sent = len(
        packets
    )

    successful_packets = [
        packet
        for packet in packets
        if packet.successful
    ]

    packets_received = len(
        successful_packets
    )

    packets_lost = (
        packets_sent
        - packets_received
    )

    packet_loss_pct = (
        packets_lost
        / packets_sent
        * 100.0
    )


    # --------------------------------------------------------
    # RSSI
    # --------------------------------------------------------

    rssi_values = [
        packet.rssi_dbm

        for packet in packets

        if packet.rssi_dbm
        is not None
    ]

    rssi_mean = (
        mean_or_none(
            rssi_values
        )
    )


    # --------------------------------------------------------
    # RTT / latency
    # --------------------------------------------------------

    rtts = [
        packet.rtt_ms

        for packet
        in successful_packets

        if packet.rtt_ms
        is not None
    ]

    latency_mean = (
        mean_or_none(
            rtts
        )
    )

    latency_min = (
        min(rtts)
        if rtts
        else None
    )

    latency_max = (
        max(rtts)
        if rtts
        else None
    )

    jitter = (
        calculate_jitter(
            rtts
        )
    )


    # --------------------------------------------------------
    # Throughput
    #
    # Application-payload throughput only.
    # --------------------------------------------------------

    successful_bytes = sum(
        packet.payload_bytes
        for packet
        in successful_packets
    )

    duration_seconds = (
        window.elapsed_seconds
    )

    throughput_kbps = (
        successful_bytes
        * 8
        / duration_seconds
        / 1000
    )


    # --------------------------------------------------------
    # Retry count
    # --------------------------------------------------------

    total_retries = sum(
        packet.retries
        for packet in packets
    )


    # --------------------------------------------------------
    # Overall communication status
    # --------------------------------------------------------

    successful = (
        packets_received > 0
    )


    # ========================================================
    # DATABASE / FASTAPI PAYLOAD
    #
    # These keys map directly to your team's MeasurementIn.
    # ========================================================

    return {

        # ----------------------------------------------------
        # Identification
        # ----------------------------------------------------

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "experiment_id":
            build_experiment_id(
                repetition
            ),

        "protocol":
            PROTOCOL,

        "radio_family":
            RADIO_FAMILY,

        "source_node":
            SOURCE_NODE,

        "destination_node":
            DESTINATION_NODE,


        # ----------------------------------------------------
        # FACTOR 1 — DISTANCE
        # ----------------------------------------------------

        "distance_m":
            DISTANCE_M,


        # ----------------------------------------------------
        # FACTOR 4 — ENVIRONMENT
        # ----------------------------------------------------

        "environment":
            ENVIRONMENT,


        # ----------------------------------------------------
        # FACTOR 5 — VISIBILITY
        # ----------------------------------------------------

        "line_of_sight":
            LINE_OF_SIGHT,


        # ----------------------------------------------------
        # FACTOR 6 — OBSTACLE
        # ----------------------------------------------------

        "obstacle_type":
            OBSTACLE_TYPE,


        # ----------------------------------------------------
        # Additional physical metadata
        # ----------------------------------------------------

        "mobility":
            MOBILITY,

        "interference_level":
            INTERFERENCE_LEVEL,


        # ----------------------------------------------------
        # FACTOR 2 — PAYLOAD
        #
        # Notice that this comes from the ESP32-observed
        # payload after validation.
        # ----------------------------------------------------

        "payload_bytes":
            actual_payload_bytes,


        # ----------------------------------------------------
        # FACTOR 3 — PACKET INTERVAL
        # ----------------------------------------------------

        "packet_interval_ms":
            PACKET_INTERVAL_MS,


        # ----------------------------------------------------
        # Measured number of packets in this timed repetition
        # ----------------------------------------------------

        "packet_count":
            packets_sent,


        # ----------------------------------------------------
        # FACTOR 7 — TRAFFIC REQUIREMENT
        # ----------------------------------------------------

        "traffic_type":
            TRAFFIC_REQUIREMENT,


        # ----------------------------------------------------
        # Application requirements
        # ----------------------------------------------------

        "qos_priority":
            QOS_PRIORITY,

        "required_latency_ms":
            REQUIRED_LATENCY_MS,

        "required_throughput_kbps":
            REQUIRED_THROUGHPUT_KBPS,

        "reliability_requirement":
            RELIABILITY_REQUIREMENT,

        "power_priority":
            POWER_PRIORITY,

        "range_requirement_m":
            RANGE_REQUIREMENT_M,


        # ----------------------------------------------------
        # Radio measurements
        # ----------------------------------------------------

        "rssi_dbm":
            rssi_mean,

        "snr_db":
            None,

        # Leave raw DB measurement empty.
        # Calculate link/utility score later.
        "link_quality":
            None,

        "tx_power_dbm":
            TX_POWER_DBM,


        # ----------------------------------------------------
        # Reliability measurements
        # ----------------------------------------------------

        "packets_sent":
            packets_sent,

        "packets_received":
            packets_received,

        "packets_lost":
            packets_lost,

        "packet_loss_pct":
            packet_loss_pct,


        # ----------------------------------------------------
        # Latency measurements
        # ----------------------------------------------------

        "rtt_ms":
            None,

        "latency_mean_ms":
            latency_mean,

        "latency_min_ms":
            latency_min,

        "latency_max_ms":
            latency_max,

        "jitter_ms":
            jitter,


        # ----------------------------------------------------
        # Throughput
        # ----------------------------------------------------

        "throughput_kbps":
            throughput_kbps,


        # ----------------------------------------------------
        # FACTOR 8 — TEST DURATION
        #
        # MeasurementIn currently has no
        # test_duration_seconds column, so measured duration
        # is represented through transfer_time_ms.
        # ----------------------------------------------------

        "transfer_time_ms":
            duration_seconds
            * 1000.0,


        # ----------------------------------------------------
        # Reliability / connection
        # ----------------------------------------------------

        "retries":
            total_retries,

        "connection_setup_ms":
            None,

        "disconnect_count":
            None,


        # ----------------------------------------------------
        # Power
        # ----------------------------------------------------

        "battery_voltage":
            BATTERY_VOLTAGE,

        "current_ma":
            CURRENT_MA,

        "estimated_energy_mj":
            None,


        # ----------------------------------------------------
        # Wi-Fi
        # ----------------------------------------------------

        "wifi_channel":
            WIFI_CHANNEL,


        # ----------------------------------------------------
        # BLE
        # ----------------------------------------------------

        "ble_phy":
            BLE_PHY,


        # ----------------------------------------------------
        # Bluetooth Classic
        # ----------------------------------------------------

        "bt_mode":
            BT_MODE,


        # ----------------------------------------------------
        # LoRa
        # ----------------------------------------------------

        "lora_sf":
            LORA_SF,

        "lora_bw":
            LORA_BW,

        "lora_cr":
            LORA_CR,


        # ----------------------------------------------------
        # Cellular
        # ----------------------------------------------------

        "cellular_generation":
            CELLULAR_GENERATION,

        "cell_signal_dbm":
            CELL_SIGNAL_DBM,


        # ----------------------------------------------------
        # Overall status
        # ----------------------------------------------------

        "successful":
            successful,
    }

# ============================================================
#                    API HEALTH CHECK
# ============================================================

def check_api() -> bool:

    try:

        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=HTTP_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:

            print(
                "[API] Connected:",
                response.json(),
            )

            return True

        print(
            "[API] Health check failed:",
            response.status_code,
        )

        return False

    except requests.RequestException as exc:

        print(
            "[API] Cannot reach API:",
            exc,
        )

        return False

# ============================================================
#                      SEND TO API
# ============================================================

def send_measurement(
    measurement: dict,
) -> bool:

    try:

        response = requests.post(
            MEASUREMENT_ENDPOINT,
            json=measurement,
            timeout=HTTP_TIMEOUT_SECONDS,
        )

        if response.status_code == 201:

            result = (
                response.json()
            )

            print(
                "[DB] Stored successfully."
            )

            print(
                "[DB] ID(s):",
                result.get("ids"),
            )

            return True

        print()
        print(
            "[API ERROR]",
            response.status_code,
        )

        print(
            response.text
        )

        return False

    except requests.RequestException as exc:

        print(
            "[API ERROR]",
            exc,
        )

        return False

# ============================================================
#                  SAVE FAILED REQUEST
# ============================================================

def save_failed_measurement(
    measurement: dict,
) -> None:

    with FAILED_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            json.dumps(
                measurement
            )
            + "\n"
        )

    print(
        "[BACKUP] Saved measurement to",
        FAILED_FILE,
    )

# ============================================================
#              DISPLAY EXPERIMENT SETTINGS
# ============================================================

def print_experiment_configuration() -> None:

    print()
    print("=" * 68)
    print("ADAPTIVE IoT NETWORK EXPERIMENT")
    print("=" * 68)

    print(
        f"Protocol             : {PROTOCOL}"
    )

    print(
        f"Distance             : {DISTANCE_M} m"
    )

    print(
        f"Payload              : {PAYLOAD_BYTES} bytes"
    )

    print(
        f"Packet interval      : {PACKET_INTERVAL_MS} ms"
    )

    print(
        f"Environment          : {ENVIRONMENT}"
    )

    print(
        "Visibility           : "
        + (
            "LoS"
            if LINE_OF_SIGHT
            else "NLoS"
        )
    )

    print(
        f"Obstacle             : "
        f"{OBSTACLE_TYPE or 'NONE'}"
    )

    print(
        f"Traffic requirement  : "
        f"{TRAFFIC_REQUIREMENT}"
    )

    print(
        f"Test duration        : "
        f"{TEST_DURATION_SECONDS} seconds"
    )

    print(
        f"Repetitions          : "
        f"{REPETITIONS}"
    )

    print("=" * 68)
    print()

# ============================================================
#                  RESULT SUMMARY
# ============================================================

def print_measurement_summary(
    measurement: dict,
    repetition: int,
) -> None:

    print()
    print("=" * 68)

    print(
        f"RESULT — REPETITION "
        f"{repetition}/{REPETITIONS}"
    )

    print(
        f"Experiment ID : "
        f"{measurement['experiment_id']}"
    )

    print(
        "Packets       : "
        f"{measurement['packets_received']}"
        "/"
        f"{measurement['packets_sent']}"
    )

    print(
        "Packet loss   : "
        f"{measurement['packet_loss_pct']:.2f}%"
    )

    if measurement[
        "rssi_dbm"
    ] is not None:

        print(
            "Mean RSSI     : "
            f"{measurement['rssi_dbm']:.2f} dBm"
        )

    if measurement[
        "latency_mean_ms"
    ] is not None:

        print(
            "Mean RTT      : "
            f"{measurement['latency_mean_ms']:.2f} ms"
        )

    if measurement[
        "jitter_ms"
    ] is not None:

        print(
            "Jitter        : "
            f"{measurement['jitter_ms']:.2f} ms"
        )

    print(
        "Throughput    : "
        f"{measurement['throughput_kbps']:.3f} kbps"
    )

    print(
        "Test duration : "
        f"{measurement['transfer_time_ms'] / 1000:.2f} s"
    )

    print("=" * 68)
    print()

# ============================================================
#                 COLLECT ONE REPETITION
# ============================================================

def collect_repetition(
    ser: serial.Serial,
    repetition: int,
) -> MeasurementWindow:

    window = (
        MeasurementWindow()
    )

    # Clear any old packets from previous experiment.
    ser.reset_input_buffer()

    window.start()

    print()
    print(
        f"[TEST] Starting repetition "
        f"{repetition}/{REPETITIONS}"
    )

    print(
        "[TEST]",
        build_experiment_id(
            repetition
        ),
    )

    print(
        f"[TEST] Duration: "
        f"{TEST_DURATION_SECONDS}s"
    )

    while (
        window.elapsed_seconds
        < TEST_DURATION_SECONDS
    ):

        raw = (
            ser.readline()
        )

        if not raw:
            continue

        line = (
            raw.decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )

        if not line:
            continue

        if not line.startswith(
            "PKT,"
        ):

            print(
                "[ESP]",
                line,
            )

            continue

        packet = (
            parse_packet_line(
                line
            )
        )

        if packet is None:
            continue

        # Prevent incorrectly labelled data.
        if not validate_packet_configuration(
            packet
        ):
            continue

        window.add(
            packet
        )

        status = (
            "OK"
            if packet.successful
            else "LOST"
        )

        rtt_text = (
            f"{packet.rtt_ms:.2f}ms"
            if packet.rtt_ms
            is not None
            else "-"
        )

        print(
            f"[PKT] "
            f"id={packet.packet_id:<6d} "
            f"{status:<4s} "
            f"payload={packet.payload_bytes:<4d}B "
            f"RSSI={packet.rssi_dbm:6.1f} "
            f"RTT={rtt_text:>9s}"
        )

    window.stop()

    return window

# ============================================================
#                          MAIN
# ============================================================

def main() -> None:
    validate_configuration()
    print_experiment_configuration()
    check_api()

    while True:

        try:

            print(
                f"[SERIAL] Opening "
                f"{SERIAL_PORT} "
                f"@ {BAUD_RATE}"
            )

            with serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                timeout=1,
            ) as ser:

                # ESP32 may reset when serial port opens
                time.sleep(2)

                print(
                    "[SERIAL] Connected"
                )

                # Configure sender automatically
                configure_esp32(
                    ser
                )

                # Remove any remaining config/debug messages
                ser.reset_input_buffer()


                # ============================================
                # RUN ALL REPETITIONS
                # ============================================

                for repetition in range(
                    1,
                    REPETITIONS + 1,
                ):

                    window = (
                        collect_repetition(
                            ser,
                            repetition,
                        )
                    )


                    if not window.packets:

                        print(
                            "[WARNING] No valid packets "
                            "collected during this repetition."
                        )

                        continue


                    measurement = (
                        build_measurement(
                            window,
                            repetition,
                        )
                    )


                    print_measurement_summary(
                        measurement,
                        repetition,
                    )


                    success = (
                        send_measurement(
                            measurement
                        )
                    )


                    if not success:

                        save_failed_measurement(
                            measurement
                        )


                    # Separation between independent runs.
                    if (
                        repetition
                        < REPETITIONS
                    ):

                        print(
                            "[TEST] Waiting 3 seconds "
                            "before next repetition..."
                        )

                        time.sleep(3)


                print()
                print(
                    "[DONE] Experiment completed."
                )

                return


        except SerialException as exc:

            print(
                "[SERIAL ERROR]",
                exc,
            )

            print(
                "Retrying in 3 seconds..."
            )

            time.sleep(3)


        except KeyboardInterrupt:

            print()
            print(
                "Collector stopped by user."
            )

            sys.exit(0)

if __name__ == "__main__":
    main()