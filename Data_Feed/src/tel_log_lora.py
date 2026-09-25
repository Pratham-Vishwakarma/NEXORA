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
#
# Must match the LoRa sender configuration.
# ------------------------------------------------------------

PAYLOAD_BYTES = 16


# ------------------------------------------------------------
# 3. PACKET INTERVAL
#
# Must match the LoRa sender configuration.
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


# ------------------------------------------------------------
# 7. TRAFFIC REQUIREMENT
# ------------------------------------------------------------

TRAFFIC_REQUIREMENT = "TELEMETRY"


# ------------------------------------------------------------
# 8. TEST DURATION
# ------------------------------------------------------------

TEST_DURATION_SECONDS = 20


# ------------------------------------------------------------
# 9. REPETITIONS
# ------------------------------------------------------------

REPETITIONS = 3


# ------------------------------------------------------------
# Maximum supported payload in your current LoRa sketch.
# ------------------------------------------------------------

MAX_PAYLOAD_BYTES = 1024


# ============================================================
#                PROTOCOL / DEVICE SETTINGS
# ============================================================

PROTOCOL = "LORA"

RADIO_FAMILY = "LPWAN"

SOURCE_NODE = "ARDUINO_UNO_A"

DESTINATION_NODE = "ARDUINO_UNO_B"


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


# ============================================================
#                    POWER SETTINGS
# ============================================================

# Constant voltage across the measured LoRa load.

SUPPLY_VOLTAGE_V = 3.3


# ============================================================
#                PROTOCOL-SPECIFIC VALUES
# ============================================================

# ------------------------------------------------------------
# Wi-Fi
# ------------------------------------------------------------

WIFI_CHANNEL = None


# ------------------------------------------------------------
# BLE
# ------------------------------------------------------------

BLE_PHY = None


# ------------------------------------------------------------
# Bluetooth Classic
# ------------------------------------------------------------

BT_MODE = None


# ------------------------------------------------------------
# LoRa
# ------------------------------------------------------------

LORA_SF = 7

LORA_BW = 125.0

LORA_CR = "4/5"

TX_POWER_DBM = 17


# ------------------------------------------------------------
# Cellular
# ------------------------------------------------------------

CELLULAR_GENERATION = None

CELL_SIGNAL_DBM = None


# ============================================================
#                  SERIAL CONFIGURATION
# ============================================================

SERIAL_PORT = "COM8"

BAUD_RATE = 115200

SERIAL_TIMEOUT_SECONDS = 1.0


# ============================================================
#                    API CONFIGURATION
# ============================================================

API_BASE_URL = "http://192.168.12.50:8000"

MEASUREMENT_ENDPOINT = (
    f"{API_BASE_URL}/measurements"
)

HTTP_TIMEOUT_SECONDS = 5


# ============================================================
#                  LOCAL FAILURE BACKUP
# ============================================================

FAILED_FILE = Path(
    "data_feed/errors/failed_measurements.jsonl"
)


# ============================================================
#                   PACKET DATA MODEL
# ============================================================

@dataclass
class PacketTelemetry:

    packet_id: int

    payload_bytes: int

    rssi_dbm: float | None

    snr_db: float | None

    rtt_ms: float | None

    successful: bool

    timestamp_ms: int


# ============================================================
#                    POWER DATA MODEL
# ============================================================

@dataclass
class PowerSample:

    timestamp_ms: int

    current_ma: float


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
            "_"
        )
        .replace(
            "-",
            "_"
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
            "p"
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
        f"sf{LORA_SF}_"
        f"bw{int(LORA_BW)}khz_"
        f"t{TEST_DURATION_SECONDS}s_"
        f"rep{repetition:02d}"
    )


# ============================================================
#                LORA SENDER CONFIGURATION
# ============================================================

def configure_lora_sender(
    ser: serial.Serial,
) -> None:

    # --------------------------------------------------------
    # Remove stale serial data.
    # --------------------------------------------------------

    ser.reset_input_buffer()


    # --------------------------------------------------------
    # Configure payload size.
    # --------------------------------------------------------

    size_command = (
        f"SIZE,"
        f"{PAYLOAD_BYTES}\n"
    )

    ser.write(
        size_command.encode(
            "utf-8"
        )
    )

    ser.flush()

    time.sleep(
        0.2
    )


    # --------------------------------------------------------
    # Configure packet interval.
    # --------------------------------------------------------

    interval_command = (
        f"INTERVAL,"
        f"{PACKET_INTERVAL_MS}\n"
    )

    ser.write(
        interval_command.encode(
            "utf-8"
        )
    )

    ser.flush()

    time.sleep(
        0.2
    )


    # --------------------------------------------------------
    # Read sender confirmation.
    # --------------------------------------------------------

    confirmed_payload = None

    confirmed_interval = None

    timeout_at = (
        time.monotonic()
        + 5.0
    )

    while (
        time.monotonic()
        <
        timeout_at
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

        print(
            "[UNO]",
            line
        )

        if line.startswith(
            "CONFIG_OK,"
        ):

            parts = (
                line.split(
                    ","
                )
            )

            if len(
                parts
            ) != 3:

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
                ==
                PAYLOAD_BYTES
                and
                confirmed_interval
                ==
                PACKET_INTERVAL_MS
            ):

                print(
                    "[CONFIG] LoRa sender "
                    "configuration confirmed"
                )

                return


    # --------------------------------------------------------
    # If confirmation was not observed, explicitly ask for it.
    # --------------------------------------------------------

    ser.write(
        b"CONFIG\n"
    )

    ser.flush()

    timeout_at = (
        time.monotonic()
        + 3.0
    )

    while (
        time.monotonic()
        <
        timeout_at
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

        print(
            "[UNO]",
            line
        )

        if not line.startswith(
            "CONFIG_OK,"
        ):

            continue

        parts = (
            line.split(
                ","
            )
        )

        if len(
            parts
        ) != 3:

            continue

        confirmed_payload = int(
            parts[1]
        )

        confirmed_interval = int(
            parts[2]
        )

        if (
            confirmed_payload
            !=
            PAYLOAD_BYTES
        ):

            raise RuntimeError(
                "LoRa payload "
                "confirmation mismatch"
            )

        if (
            confirmed_interval
            !=
            PACKET_INTERVAL_MS
        ):

            raise RuntimeError(
                "LoRa interval "
                "confirmation mismatch"
            )

        print(
            "[CONFIG] LoRa sender "
            "configuration confirmed"
        )

        return


    raise RuntimeError(
        "LoRa sender did not confirm "
        "configuration"
    )


# ============================================================
#                 RESET ENERGY MEASUREMENT
# ============================================================

def reset_energy_measurement(
    ser: serial.Serial,
) -> None:

    ser.write(
        b"ENERGY_RESET\n"
    )

    ser.flush()

    timeout_at = (
        time.monotonic()
        + 2.0
    )

    while (
        time.monotonic()
        <
        timeout_at
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

        if line.startswith(
            "ENERGY_RESET_OK"
        ):

            print(
                "[POWER] Energy "
                "measurement reset"
            )

            return

        print(
            "[UNO]",
            line
        )

    print(
        "[WARN] ENERGY_RESET_OK "
        "was not received"
    )


# ============================================================
#                    SERIAL PARSER
# ============================================================

def parse_packet_line(
    line: str,
) -> PacketTelemetry | None:

    """
    Expected LoRa sender format:

    PKT,
    packet_id,
    payload_bytes,
    rssi_dbm,
    snr_db,
    rtt_ms,
    successful,
    current_ma,
    voltage_v,
    cumulative_energy_mj,
    timestamp_ms

    Example:

    PKT,21,16,-37,10.25,76.41,1,42.51,3.30,143.22,12844

    The current/energy values inside the PKT line are not used
    as the main experiment energy source if independent PWR
    samples are available.

    This parser extracts the packet/network metrics.
    """

    if not line.startswith(
        "PKT,"
    ):

        return None

    parts = (
        line.split(
            ","
        )
    )

    if len(
        parts
    ) != 11:

        print(
            f"[WARN] Expected 11 PKT fields, "
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

        rssi_value = float(
            parts[3]
        )

        snr_value = float(
            parts[4]
        )

        rtt_value = float(
            parts[5]
        )

        successful = bool(
            int(
                parts[6]
            )
        )

        timestamp_ms = int(
            parts[10]
        )


        # ----------------------------------------------------
        # Failed ACK packets use placeholder zero RSSI/SNR.
        # Don't treat those as valid radio measurements.
        # ----------------------------------------------------

        if successful:

            rssi_dbm = (
                rssi_value
            )

            snr_db = (
                snr_value
            )

        else:

            rssi_dbm = None

            snr_db = None


        return PacketTelemetry(

            packet_id=
                packet_id,

            payload_bytes=
                payload_bytes,

            rssi_dbm=
                rssi_dbm,

            snr_db=
                snr_db,

            rtt_ms=(
                None
                if rtt_value < 0
                else rtt_value
            ),

            successful=
                successful,

            timestamp_ms=
                timestamp_ms,
        )

    except ValueError as exc:

        print(
            f"[WARN] PKT parse error: "
            f"{exc}: "
            f"{line}"
        )

        return None


# ============================================================
#                 PARSE POWER SAMPLE
# ============================================================

def parse_power_line(
    line: str,
) -> PowerSample | None:

    """
    Expected:

    PWR,timestamp_ms,current_ma

    Example:

    PWR,12840,41.762
    """

    if not line.startswith(
        "PWR,"
    ):

        return None

    parts = (
        line.split(
            ","
        )
    )

    if len(
        parts
    ) != 3:

        print(
            f"[WARN] Expected 3 PWR fields, "
            f"got {len(parts)}: "
            f"{line}"
        )

        return None

    try:

        return PowerSample(

            timestamp_ms=
                int(
                    parts[1]
                ),

            current_ma=
                float(
                    parts[2]
                ),
        )

    except ValueError as exc:

        print(
            f"[WARN] PWR parse error: "
            f"{exc}: "
            f"{line}"
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

        self.power_samples: list[
            PowerSample
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

        self.power_samples.clear()

        self.started_at = (
            time.monotonic()
        )

        self.finished_at = None


    def add_packet(
        self,
        packet: PacketTelemetry,
    ) -> None:

        self.packets.append(
            packet
        )


    def add_power(
        self,
        sample: PowerSample,
    ) -> None:

        self.power_samples.append(
            sample
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
            -
            self.started_at,
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

    if len(
        rtts
    ) < 2:

        return None

    differences = [

        abs(
            current
            -
            previous
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
        DISTANCE_M
        <
        0
    ):

        raise ValueError(
            "DISTANCE_M cannot be negative"
        )


    if not (
        1
        <=
        PAYLOAD_BYTES
        <=
        MAX_PAYLOAD_BYTES
    ):

        raise ValueError(
            f"PAYLOAD_BYTES must be between "
            f"1 and {MAX_PAYLOAD_BYTES}"
        )


    if (
        PACKET_INTERVAL_MS
        <=
        0
    ):

        raise ValueError(
            "PACKET_INTERVAL_MS must be > 0"
        )


    if (
        TEST_DURATION_SECONDS
        <=
        0
    ):

        raise ValueError(
            "TEST_DURATION_SECONDS must be > 0"
        )


    if (
        REPETITIONS
        <
        1
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
            "ENVIRONMENT must be "
            "'INDOOR' or 'OPEN'"
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
            "OBSTACLE_TYPE must be "
            "None, 'WALL', or 'PEOPLE'"
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
            "TRAFFIC_REQUIREMENT must be "
            "'TELEMETRY', 'INTERACTIVE', "
            "or 'BULK'"
        )


# ============================================================
#             PACKET CONFIGURATION VALIDATION
# ============================================================

def validate_packet_configuration(
    packet: PacketTelemetry,
) -> bool:

    if (
        packet.payload_bytes
        !=
        PAYLOAD_BYTES
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
            f"Arduino payload      : "
            f"{packet.payload_bytes}"
        )

        print(
            "Measurement will NOT "
            "be added."
        )

        print()

        return False

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


    # ========================================================
    # Validate payload sizes
    # ========================================================

    actual_payload_sizes = {

        packet.payload_bytes

        for packet
        in packets
    }

    if (
        len(
            actual_payload_sizes
        )
        !=
        1
    ):

        raise ValueError(
            "Mixed payload sizes detected "
            f"inside experiment: "
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
        !=
        PAYLOAD_BYTES
    ):

        raise ValueError(
            f"Python configured "
            f"{PAYLOAD_BYTES} B, "
            f"but Arduino transmitted "
            f"{actual_payload_bytes} B"
        )


    # ========================================================
    # Packet counts
    # ========================================================

    packets_sent = (
        len(
            packets
        )
    )

    successful_packets = [

        packet

        for packet
        in packets

        if packet.successful
    ]

    packets_received = (
        len(
            successful_packets
        )
    )

    packets_lost = (
        packets_sent
        -
        packets_received
    )

    packet_loss_pct = (

        packets_lost
        /
        packets_sent
        *
        100.0
    )


    # ========================================================
    # RSSI
    # ========================================================

    rssi_values = [

        packet.rssi_dbm

        for packet
        in successful_packets

        if packet.rssi_dbm
        is not None
    ]

    rssi_mean = (
        mean_or_none(
            rssi_values
        )
    )


    # ========================================================
    # SNR
    # ========================================================

    snr_values = [

        packet.snr_db

        for packet
        in successful_packets

        if packet.snr_db
        is not None
    ]

    snr_mean = (
        mean_or_none(
            snr_values
        )
    )


    # ========================================================
    # RTT / latency
    # ========================================================

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


    # ========================================================
    # Throughput
    #
    # Application payload only.
    # ========================================================

    successful_bytes = sum(

        packet.payload_bytes

        for packet
        in successful_packets
    )

    duration_seconds = float(
        TEST_DURATION_SECONDS
    )

    throughput_kbps = (

        successful_bytes
        *
        8
        /
        duration_seconds
        /
        1000
    )


    # ========================================================
    # Power / Energy
    #
    # Same logic as your Wi-Fi collector:
    #
    # independent PWR samples ->
    # mean current ->
    # E = V * I * t
    #
    # ========================================================

    current_values = [

        sample.current_ma

        for sample
        in window.power_samples
    ]

    current_mean_ma = (
        mean_or_none(
            current_values
        )
    )

    estimated_energy_mj = (

        SUPPLY_VOLTAGE_V
        *
        current_mean_ma
        *
        duration_seconds

        if current_mean_ma
        is not None

        else None
    )


    # ========================================================
    # Communication status
    # ========================================================

    successful = (
        packets_received
        >
        0
    )


    # ========================================================
    # DATABASE / FASTAPI PAYLOAD
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
        # Physical conditions
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Traffic
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Radio measurements
        # ----------------------------------------------------

        "rssi_dbm":
            rssi_mean,

        "snr_db":
            snr_mean,

        "link_quality":
            None,

        "tx_power_dbm":
            TX_POWER_DBM,


        # ----------------------------------------------------
        # Reliability
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
        # Latency
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Throughput
        # ----------------------------------------------------

        "throughput_kbps":
            throughput_kbps,


        # ----------------------------------------------------
        # Test duration
        # ----------------------------------------------------

        "transfer_time_ms":
            TEST_DURATION_SECONDS
            *
            1000.0,


        # ----------------------------------------------------
        # Retry / connection
        #
        # Current LoRa sender has ACK success/failure,
        # but does not perform retransmissions.
        # ----------------------------------------------------

        "retries":
            0,

        "connection_setup_ms":
            None,

        "disconnect_count":
            None,


        # ----------------------------------------------------
        # POWER
        # ----------------------------------------------------

        "battery_voltage":
            SUPPLY_VOLTAGE_V,

        "current_ma":
            current_mean_ma,

        "estimated_energy_mj":
            estimated_energy_mj,


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
        # Overall communication status
        # ----------------------------------------------------

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
            ==
            200
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
            ==
            201
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

    FAILED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with FAILED_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:

        file.write(

            json.dumps(
                measurement
            )
            +
            "\n"
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
        f"Distance             : "
        f"{DISTANCE_M} m"
    )

    print(
        f"Payload              : "
        f"{PAYLOAD_BYTES} bytes"
    )

    print(
        f"Packet interval      : "
        f"{PACKET_INTERVAL_MS} ms"
    )

    print(
        f"Environment          : "
        f"{ENVIRONMENT}"
    )

    print(
        "Visibility           : "
        +
        (
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
        f"LoRa SF              : "
        f"SF{LORA_SF}"
    )

    print(
        f"LoRa bandwidth       : "
        f"{LORA_BW:.0f} kHz"
    )

    print(
        f"LoRa coding rate     : "
        f"{LORA_CR}"
    )

    print(
        f"LoRa TX power        : "
        f"{TX_POWER_DBM} dBm"
    )

    print(
        f"Supply voltage       : "
        f"{SUPPLY_VOLTAGE_V:.2f} V"
    )

    print(
        f"Test duration        : "
        f"{TEST_DURATION_SECONDS} seconds"
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


    if (
        measurement[
            "snr_db"
        ]
        is not None
    ):

        print(
            "Mean SNR      : "
            f"{measurement['snr_db']:.2f} dB"
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


    print(
        "Throughput    : "
        f"{measurement['throughput_kbps']:.4f} kbps"
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


    print(
        "Supply voltage: "
        f"{measurement['battery_voltage']:.2f} V"
    )


    if (
        measurement[
            "estimated_energy_mj"
        ]
        is not None
    ):

        print(
            "Est. energy   : "
            f"{measurement['estimated_energy_mj']:.2f} mJ"
        )

    else:

        print(
            "Est. energy   : N/A"
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


    # --------------------------------------------------------
    # Clear stale serial information.
    # --------------------------------------------------------

    ser.reset_input_buffer()


    # --------------------------------------------------------
    # Reset Arduino-side experiment energy state.
    # --------------------------------------------------------

    reset_energy_measurement(
        ser
    )


    # --------------------------------------------------------
    # Clear anything printed by reset.
    # --------------------------------------------------------

    ser.reset_input_buffer()


    window.start()


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
        f"[TEST] Duration: "
        f"{TEST_DURATION_SECONDS}s"
    )


    while (
        window.elapsed_seconds
        <
        TEST_DURATION_SECONDS
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


        # ----------------------------------------------------
        # Independent ACS712 current sample
        # ----------------------------------------------------

        if line.startswith(
            "PWR,"
        ):

            sample = (
                parse_power_line(
                    line
                )
            )

            if (
                sample
                is not None
            ):

                window.add_power(
                    sample
                )

            continue


        # ----------------------------------------------------
        # Debug/status messages
        # ----------------------------------------------------

        if not line.startswith(
            "PKT,"
        ):

            print(
                "[UNO]",
                line,
            )

            continue


        # ----------------------------------------------------
        # Packet telemetry
        # ----------------------------------------------------

        packet = (
            parse_packet_line(
                line
            )
        )

        if (
            packet
            is None
        ):

            continue


        if not (
            validate_packet_configuration(
                packet
            )
        ):

            continue


        window.add_packet(
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

            f"{packet.rssi_dbm:.1f}"

            if packet.rssi_dbm
            is not None

            else "-"
        )


        snr_text = (

            f"{packet.snr_db:.2f}"

            if packet.snr_db
            is not None

            else "-"
        )


        print(

            f"[PKT] "

            f"id="
            f"{packet.packet_id:<6d} "

            f"{status:<4s} "

            f"payload="
            f"{packet.payload_bytes:<4d}B "

            f"RSSI="
            f"{rssi_text:>6s} "

            f"SNR="
            f"{snr_text:>6s} "

            f"RTT="
            f"{rtt_text:>9s}"
        )


    window.stop()

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

                timeout=
                    SERIAL_TIMEOUT_SECONDS,

            ) as ser:


                # ------------------------------------------------
                # Arduino UNO may reset when serial is opened.
                # ------------------------------------------------

                time.sleep(
                    2
                )


                print(
                    "[SERIAL] Connected"
                )


                # ------------------------------------------------
                # Configure sender automatically.
                # ------------------------------------------------

                configure_lora_sender(
                    ser
                )


                ser.reset_input_buffer()


                # ================================================
                # RUN REPETITIONS
                # ================================================

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


                    if not (
                        window.packets
                    ):

                        print(
                            "[WARNING] No valid packets "
                            "collected during this "
                            "repetition."
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


                    # ------------------------------------------------
                    # Show exact API payload.
                    # ------------------------------------------------

                    print(
                        "[DATA] Measurement payload:"
                    )

                    print(
                        json.dumps(
                            measurement,
                            indent=2,
                        )
                    )

                    print()


                    # ------------------------------------------------
                    # Upload to database.
                    # ------------------------------------------------

                    success = (
                        send_measurement(
                            measurement
                        )
                    )


                    if not success:

                        save_failed_measurement(
                            measurement
                        )


                    # ------------------------------------------------
                    # Separation between repetitions.
                    # ------------------------------------------------

                    if (
                        repetition
                        <
                        REPETITIONS
                    ):

                        print(
                            "[TEST] Waiting "
                            "3 seconds before "
                            "next repetition..."
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