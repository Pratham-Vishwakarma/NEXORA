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

DISTANCE_M = 0.0

PAYLOAD_BYTES = 16

PACKET_INTERVAL_MS = 100

ENVIRONMENT = "INDOOR"

LINE_OF_SIGHT = True

OBSTACLE_TYPE = None

TRAFFIC_REQUIREMENT = "TELEMETRY"

TEST_DURATION_SECONDS = 20

REPETITIONS = 1

MAX_PAYLOAD_BYTES = 2048


# ============================================================
#                PROTOCOL / DEVICE SETTINGS
# ============================================================

PROTOCOL = "BLUETOOTH"

RADIO_FAMILY = "BLUETOOTH_CLASSIC"

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

BATTERY_VOLTAGE = 3.3


# ============================================================
#                PROTOCOL-SPECIFIC VALUES
# ============================================================

WIFI_CHANNEL = None

BLE_PHY = None

BT_MODE = "SPP"

LORA_SF = None

LORA_BW = None

LORA_CR = None

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

API_BASE_URL = (
    "http://100.72.37.28:8000"
)

MEASUREMENT_ENDPOINT = (
    f"{API_BASE_URL}/measurements"
)

HTTP_TIMEOUT_SECONDS = 5


# ============================================================
#                  LOCAL FAILURE BACKUP
# ============================================================

FAILED_FILE = Path(
    "E:/Projects/Project_Nexora/Data_Feed/errors/"
    "failed_measurements.jsonl"
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

    current_ma: float | None

    energy_mj: float | None


# ============================================================
#                EXPERIMENT-ID GENERATION
# ============================================================

def normalise_name(
    value: str,
) -> str:

    return (
        value
        .strip()
        .lower()
        .replace(
            " ",
            "_",
        )
        .replace(
            "-",
            "_",
        )
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
        str(
            DISTANCE_M
        )
        .replace(
            ".",
            "p",
        )
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
#                  ESP32 CONFIGURATION
# ============================================================

def configure_esp32(
    ser: serial.Serial,
) -> None:

    command = (
        f"CONFIG,"
        f"{PAYLOAD_BYTES},"
        f"{PACKET_INTERVAL_MS}\n"
    )


    ser.reset_input_buffer()


    ser.write(
        command.encode(
            "utf-8"
        )
    )


    ser.flush()


    print(
        f"[CONFIG] Sent -> "
        f"payload={PAYLOAD_BYTES} bytes, "
        f"interval={PACKET_INTERVAL_MS} ms"
    )


    timeout_at = (
        time.monotonic()
        + 5
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
            line,
        )


        if line.startswith(
            "CONFIG_OK,"
        ):

            parts = (
                line.split(",")
            )


            if (
                len(parts) != 4
            ):

                print(
                    "[WARN] Invalid CONFIG_OK:"
                )

                continue


            try:

                confirmed_payload = int(
                    parts[1]
                )

                confirmed_interval = int(
                    parts[2]
                )

            except ValueError:

                continue


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


            print(
                "[CONFIG] Protocol: "
                "Bluetooth Classic"
            )


            print(
                f"[CONFIG] Bluetooth mode: "
                f"{BT_MODE}"
            )


            print(
                "[CONFIG] Packet interval is "
                "start-to-start"
            )


            print(
                "[CONFIG] ESP32 configuration confirmed"
            )


            return


        if line.startswith(
            "CONFIG_ERROR"
        ):

            raise RuntimeError(
                "ESP32 rejected configuration: "
                f"{line}"
            )


    raise RuntimeError(
        "ESP32 did not confirm configuration "
        "within 5 seconds"
    )


# ============================================================
#                    SERIAL PARSER
# ============================================================

def parse_packet_line(
    line: str,
) -> PacketTelemetry | None:

    """
    Expected:

    PKT,
    packet_id,
    payload_bytes,
    rssi,
    rtt_ms,
    success,
    retries,
    timestamp_ms,
    current_ma,
    energy_mj
    """

    if not line.startswith(
        "PKT,"
    ):

        return None


    parts = (
        line.split(",")
    )


    if (
        len(parts) != 10
    ):

        print(
            f"[WARN] Expected 10 fields, "
            f"got {len(parts)}: "
            f"{line}"
        )

        return None


    try:

        packet_id = int(
            parts[1]
        )


        payload_bytes = int(
            parts[2]
        )


        raw_rssi = float(
            parts[3]
        )


        rssi_dbm = (

            None

            if raw_rssi <= -127

            else raw_rssi
        )


        raw_rtt = float(
            parts[4]
        )


        rtt_ms = (

            None

            if raw_rtt < 0

            else raw_rtt
        )


        successful = bool(
            int(
                parts[5]
            )
        )


        retries = int(
            parts[6]
        )


        timestamp_ms = int(
            parts[7]
        )


        raw_current = float(
            parts[8]
        )


        current_ma = (

            None

            if raw_current < 0

            else raw_current
        )


        raw_energy = float(
            parts[9]
        )


        energy_mj = (

            None

            if raw_energy < 0

            else raw_energy
        )


        return PacketTelemetry(

            packet_id=
                packet_id,

            payload_bytes=
                payload_bytes,

            rssi_dbm=
                rssi_dbm,

            rtt_ms=
                rtt_ms,

            successful=
                successful,

            retries=
                retries,

            timestamp_ms=
                timestamp_ms,

            current_ma=
                current_ma,

            energy_mj=
                energy_mj,
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

    def __init__(
        self,
    ) -> None:

        self.packets: list[
            PacketTelemetry
        ] = []


        self.started_at: (
            float | None
        ) = None


        self.finished_at: (
            float | None
        ) = None


    def start(
        self,
    ) -> None:

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


    def stop(
        self,
    ) -> None:

        self.finished_at = (
            time.monotonic()
        )


    @property
    def elapsed_seconds(
        self,
    ) -> float:

        if (
            self.started_at
            is None
        ):

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

    if (
        len(rtts) < 2
    ):

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

def validate_configuration(
) -> None:

    if (
        DISTANCE_M < 0
    ):

        raise ValueError(
            "DISTANCE_M cannot be negative"
        )


    if not (
        1
        <= PAYLOAD_BYTES
        <= MAX_PAYLOAD_BYTES
    ):

        raise ValueError(
            f"PAYLOAD_BYTES must be between "
            f"1 and {MAX_PAYLOAD_BYTES}"
        )


    if (
        PACKET_INTERVAL_MS <= 0
    ):

        raise ValueError(
            "PACKET_INTERVAL_MS must be > 0"
        )


    if (
        TEST_DURATION_SECONDS <= 0
    ):

        raise ValueError(
            "TEST_DURATION_SECONDS must be > 0"
        )


    if (
        REPETITIONS < 1
    ):

        raise ValueError(
            "REPETITIONS must be >= 1"
        )


    if (
        ENVIRONMENT
        not in {
            "INDOOR",
            "OPEN",
        }
    ):

        raise ValueError(
            "Invalid ENVIRONMENT"
        )


    if (
        OBSTACLE_TYPE
        not in {
            None,
            "WALL",
            "PEOPLE",
        }
    ):

        raise ValueError(
            "Invalid OBSTACLE_TYPE"
        )


    if (
        TRAFFIC_REQUIREMENT
        not in {
            "TELEMETRY",
            "INTERACTIVE",
            "BULK",
        }
    ):

        raise ValueError(
            "Invalid TRAFFIC_REQUIREMENT"
        )


# ============================================================
#             PACKET CONFIGURATION VALIDATION
# ============================================================

def validate_packet_configuration(
    packet: PacketTelemetry,
) -> bool:

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


        print()


        return False


    return True


# ============================================================
#              BUILD DATABASE MEASUREMENT
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


    actual_payload_sizes = {

        packet.payload_bytes

        for packet
        in packets
    }


    if (
        len(actual_payload_sizes)
        != 1
    ):

        raise ValueError(
            "Mixed payload sizes detected"
        )


    actual_payload_bytes = (
        next(
            iter(
                actual_payload_sizes
            )
        )
    )


    packets_sent = len(
        packets
    )


    successful_packets = [

        packet

        for packet
        in packets

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

        for packet
        in packets

        if packet.rssi_dbm
        is not None
    ]


    rssi_mean = (
        mean_or_none(
            rssi_values
        )
    )


    # --------------------------------------------------------
    # RTT
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
        min(
            rtts
        )
        if rtts
        else None
    )


    latency_max = (
        max(
            rtts
        )
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
    # Retries
    # --------------------------------------------------------

    total_retries = sum(

        packet.retries

        for packet
        in packets
    )


    # --------------------------------------------------------
    # Current
    # --------------------------------------------------------

    current_values = [

        packet.current_ma

        for packet
        in packets

        if packet.current_ma
        is not None
    ]


    current_mean_ma = (
        mean_or_none(
            current_values
        )
    )


    # --------------------------------------------------------
    # Energy
    #
    # Each PKT energy represents its complete start-to-start
    # transmission period.
    # --------------------------------------------------------

    energy_values = [

        packet.energy_mj

        for packet
        in packets

        if packet.energy_mj
        is not None
    ]


    estimated_energy_mj = (

        sum(
            energy_values
        )

        if energy_values

        else None
    )


    successful = (
        packets_received > 0
    )


    return {

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

        "distance_m":
            DISTANCE_M,

        "environment":
            ENVIRONMENT,

        "line_of_sight":
            LINE_OF_SIGHT,

        "obstacle_type":
            OBSTACLE_TYPE,

        "mobility":
            MOBILITY,

        "interference_level":
            INTERFERENCE_LEVEL,

        "payload_bytes":
            actual_payload_bytes,

        "packet_interval_ms":
            PACKET_INTERVAL_MS,

        "packet_count":
            packets_sent,

        "traffic_type":
            TRAFFIC_REQUIREMENT,

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

        "rssi_dbm":
            rssi_mean,

        "snr_db":
            None,

        "link_quality":
            None,

        "tx_power_dbm":
            TX_POWER_DBM,

        "packets_sent":
            packets_sent,

        "packets_received":
            packets_received,

        "packets_lost":
            packets_lost,

        "packet_loss_pct":
            packet_loss_pct,

        "rtt_ms":
            latency_mean,

        "latency_mean_ms":
            latency_mean,

        "latency_min_ms":
            latency_min,

        "latency_max_ms":
            latency_max,

        "jitter_ms":
            jitter,

        "throughput_kbps":
            throughput_kbps,

        "transfer_time_ms":
            duration_seconds
            * 1000.0,

        "retries":
            total_retries,

        "connection_setup_ms":
            None,

        "disconnect_count":
            None,

        "battery_voltage":
            BATTERY_VOLTAGE,

        "current_ma":
            current_mean_ma,

        "estimated_energy_mj":
            estimated_energy_mj,

        "wifi_channel":
            None,

        "ble_phy":
            None,

        "bt_mode":
            BT_MODE,

        "lora_sf":
            None,

        "lora_bw":
            None,

        "lora_cr":
            None,

        "cellular_generation":
            None,

        "cell_signal_dbm":
            None,

        "successful":
            successful,
    }


# ============================================================
#                    API HEALTH CHECK
# ============================================================

def check_api(
) -> bool:

    try:

        response = requests.get(

            f"{API_BASE_URL}/health",

            timeout=
                HTTP_TIMEOUT_SECONDS,
        )


        if (
            response.status_code
            == 200
        ):

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

            json=
                measurement,

            timeout=
                HTTP_TIMEOUT_SECONDS,
        )


        if (
            response.status_code
            == 201
        ):

            result = (
                response.json()
            )


            print(
                "[DB] Stored successfully."
            )


            print(
                "[DB] ID(s):",
                result.get(
                    "ids"
                ),
            )


            return True


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

    FAILED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    with FAILED_FILE.open(

        "a",

        encoding=
            "utf-8",

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

def print_experiment_configuration(
) -> None:

    print()


    print(
        "=" * 68
    )


    print(
        "ADAPTIVE IoT NETWORK EXPERIMENT"
    )


    print(
        "=" * 68
    )


    print(
        f"Protocol             : "
        f"{PROTOCOL}"
    )


    print(
        f"Radio family         : "
        f"{RADIO_FAMILY}"
    )


    print(
        f"Bluetooth mode       : "
        f"{BT_MODE}"
    )


    print(
        f"Distance             : "
        f"{DISTANCE_M} m"
    )


    print(
        f"Payload              : "
        f"{PAYLOAD_BYTES} bytes"
    )


    print(
        f"Packet interval      : "
        f"{PACKET_INTERVAL_MS} ms "
        f"(start-to-start)"
    )


    print(
        f"Environment          : "
        f"{ENVIRONMENT}"
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
        f"Dataset voltage      : "
        f"{BATTERY_VOLTAGE:.2f} V"
    )


    print(
        f"Repetitions          : "
        f"{REPETITIONS}"
    )


    print(
        "=" * 68
    )


    print()


# ============================================================
#                  RESULT SUMMARY
# ============================================================

def print_measurement_summary(
    measurement: dict,
    repetition: int,
) -> None:

    print()


    print(
        "=" * 68
    )


    print(
        f"RESULT — REPETITION "
        f"{repetition}/"
        f"{REPETITIONS}"
    )


    print(
        f"Experiment ID : "
        f"{measurement['experiment_id']}"
    )


    print(
        f"Protocol      : "
        f"{measurement['protocol']}"
    )


    print(
        f"BT Mode       : "
        f"{measurement['bt_mode']}"
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


    if (
        measurement[
            "rssi_dbm"
        ]
        is not None
    ):

        print(
            "Mean RSSI     : "
            f"{measurement['rssi_dbm']:.2f} dBm"
        )

    else:

        print(
            "Mean RSSI     : N/A"
        )


    if (
        measurement[
            "latency_mean_ms"
        ]
        is not None
    ):

        print(
            "Mean RTT      : "
            f"{measurement['latency_mean_ms']:.2f} ms"
        )

    else:

        print(
            "Mean RTT      : N/A"
        )


    if (
        measurement[
            "latency_min_ms"
        ]
        is not None
    ):

        print(
            "Minimum RTT   : "
            f"{measurement['latency_min_ms']:.2f} ms"
        )


    if (
        measurement[
            "latency_max_ms"
        ]
        is not None
    ):

        print(
            "Maximum RTT   : "
            f"{measurement['latency_max_ms']:.2f} ms"
        )


    if (
        measurement[
            "jitter_ms"
        ]
        is not None
    ):

        print(
            "Jitter        : "
            f"{measurement['jitter_ms']:.2f} ms"
        )

    else:

        print(
            "Jitter        : N/A"
        )


    print(
        "Throughput    : "
        f"{measurement['throughput_kbps']:.3f} kbps"
    )


    print(
        "Test duration : "
        f"{measurement['transfer_time_ms'] / 1000:.3f} s"
    )


    print(
        "Retries       : "
        f"{measurement['retries']}"
    )


    print(
        "-" * 68
    )


    print(
        "POWER / ENERGY"
    )


    print(
        "Voltage       : "
        f"{measurement['battery_voltage']:.2f} V"
    )


    if (
        measurement[
            "current_ma"
        ]
        is not None
    ):

        print(
            "Mean current  : "
            f"{measurement['current_ma']:.2f} mA"
        )

    else:

        print(
            "Mean current  : N/A"
        )


    if (
        measurement[
            "estimated_energy_mj"
        ]
        is not None
    ):

        print(
            "Energy        : "
            f"{measurement['estimated_energy_mj']:.3f} mJ"
        )

    else:

        print(
            "Energy        : N/A"
        )


    if (
        measurement[
            "current_ma"
        ]
        is not None
    ):

        average_power_mw = (

            measurement[
                "battery_voltage"
            ]

            *

            measurement[
                "current_ma"
            ]
        )


        print(
            "Average power : "
            f"{average_power_mw:.2f} mW"
        )


    print(
        "-" * 68
    )


    print(
        "Successful    : "
        + (
            "YES"
            if measurement[
                "successful"
            ]
            else "NO"
        )
    )


    print(
        "=" * 68
    )


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


    ser.reset_input_buffer()


    # --------------------------------------------------------
    # Temporarily reduce serial timeout.
    #
    # This prevents readline() from extending a 20-second
    # experiment by up to one whole second.
    # --------------------------------------------------------

    original_timeout = (
        ser.timeout
    )


    ser.timeout = 0.05


    window.start()


    deadline = (

        window.started_at

        + TEST_DURATION_SECONDS
    )


    print()


    print(
        f"[TEST] Starting repetition "
        f"{repetition}/"
        f"{REPETITIONS}"
    )


    print(
        "[TEST]",
        build_experiment_id(
            repetition
        ),
    )


    print(
        f"[TEST] Exact duration target: "
        f"{TEST_DURATION_SECONDS}.000 s"
    )


    print(
        f"[TEST] Packet interval: "
        f"{PACKET_INTERVAL_MS} ms "
        f"start-to-start"
    )


    print(
        f"[TEST] Bluetooth mode: "
        f"{BT_MODE}"
    )


    try:

        while (
            time.monotonic()
            < deadline
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


            if (
                packet is None
            ):

                continue


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


            rssi_text = (

                f"{packet.rssi_dbm:.1f}dBm"

                if packet.rssi_dbm
                is not None

                else "N/A"
            )


            current_text = (

                f"{packet.current_ma:.2f}mA"

                if packet.current_ma
                is not None

                else "-"
            )


            energy_text = (

                f"{packet.energy_mj:.4f}mJ"

                if packet.energy_mj
                is not None

                else "-"
            )


            print(

                f"[PKT] "
                f"id={packet.packet_id:<6d} "
                f"{status:<4s} "
                f"payload={packet.payload_bytes:<4d}B "
                f"RSSI={rssi_text:>9s} "
                f"RTT={rtt_text:>9s} "
                f"I={current_text:>11s} "
                f"E={energy_text:>13s}"
            )


    finally:

        window.stop()


        ser.timeout = (
            original_timeout
        )


    print()


    print(
        "[TEST] Collection finished"
    )


    print(
        f"[TEST] Valid packets collected: "
        f"{len(window.packets)}"
    )


    print(
        f"[TEST] Actual duration: "
        f"{window.elapsed_seconds:.3f} s"
    )


    current_values = [

        packet.current_ma

        for packet
        in window.packets

        if packet.current_ma
        is not None
    ]


    energy_values = [

        packet.energy_mj

        for packet
        in window.packets

        if packet.energy_mj
        is not None
    ]


    if current_values:

        print(
            f"[TEST] Mean current: "
            f"{statistics.fmean(current_values):.2f} mA"
        )


    if energy_values:

        print(
            f"[TEST] Integrated energy: "
            f"{sum(energy_values):.3f} mJ"
        )


    print()


    return window


# ============================================================
#                          MAIN
# ============================================================

def main(
) -> None:

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


                time.sleep(
                    2
                )


                print(
                    "[SERIAL] Connected"
                )


                configure_esp32(
                    ser
                )


                ser.reset_input_buffer()


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
                            "collected."
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


                    if (
                        repetition
                        < REPETITIONS
                    ):

                        print(
                            "[TEST] Waiting 3 seconds "
                            "before next repetition..."
                        )


                        time.sleep(
                            3
                        )


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


            time.sleep(
                3
            )


        except RuntimeError as exc:

            print(
                "[RUNTIME ERROR]",
                exc,
            )


            print(
                "Retrying in 3 seconds..."
            )


            time.sleep(
                3
            )


        except KeyboardInterrupt:

            print()


            print(
                "Collector stopped by user."
            )


            sys.exit(
                0
            )


if __name__ == "__main__":

    main()