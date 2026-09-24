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
# Python sends this value to the ESP32 using:
#
# CONFIG,<payload_bytes>,<packet_interval_ms>
#
# BLE sender currently supports 4 - 240 bytes.
# ------------------------------------------------------------

PAYLOAD_BYTES = 16


# ------------------------------------------------------------
# 3. PACKET INTERVAL
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

REPETITIONS = 1


# ------------------------------------------------------------
# Maximum supported application payload
#
# Must match BLE sender firmware.
# ------------------------------------------------------------

MAX_PAYLOAD_BYTES = 240


# ============================================================
#                PROTOCOL / DEVICE SETTINGS
# ============================================================

PROTOCOL = "BLE"

RADIO_FAMILY = "BLUETOOTH_LOW_ENERGY"

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


# ------------------------------------------------------------
# Wi-Fi
# ------------------------------------------------------------

WIFI_CHANNEL = None


# ------------------------------------------------------------
# BLE
#
# ESP32 BLE uses the LE 1M PHY for this implementation.
# ------------------------------------------------------------

BLE_PHY = "1M"


# ------------------------------------------------------------
# Bluetooth Classic
# ------------------------------------------------------------

BT_MODE = None


# ------------------------------------------------------------
# LoRa
# ------------------------------------------------------------

LORA_SF = None

LORA_BW = None

LORA_CR = None


# ------------------------------------------------------------
# Cellular
# ------------------------------------------------------------

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
#                  ESP32 CONFIGURATION
# ============================================================

# ============================================================
#                  ESP32 CONFIGURATION
# ============================================================

def configure_esp32(
    ser: serial.Serial,
) -> None:

    # ========================================================
    # STEP 1:
    # WAIT FOR BLE SENDER TO FINISH STARTUP
    #
    # Unlike Wi-Fi / Bluetooth Classic, the BLE sender does
    # not enter loop() until:
    #
    #   scan
    #   -> connect
    #   -> service discovery
    #   -> characteristic discovery
    #   -> notification registration
    #
    # have completed.
    #
    # Therefore CONFIG must NOT be sent immediately after
    # opening the serial port.
    # ========================================================

    print(
        "[CONFIG] Waiting for BLE sender "
        "to become ready..."
    )


    startup_timeout_at = (
        time.monotonic()
        + 30
    )


    ble_ready = False

    initial_config_seen = False


    while (
        time.monotonic()
        < startup_timeout_at
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
            "[ESP]",
            line
        )


        # ----------------------------------------------------
        # Sender has completed BLE setup
        # ----------------------------------------------------

        if (
            line == "BLE_READY"
        ):

            ble_ready = True

            print(
                "[CONFIG] BLE sender is ready"
            )

            continue


        # ----------------------------------------------------
        # The sender prints its DEFAULT configuration once
        # at the end of setup().
        #
        # Example:
        #
        # CONFIG_OK,16,500
        #
        # This is NOT confirmation of the Python command.
        # ----------------------------------------------------

        if (
            ble_ready
            and line.startswith(
                "CONFIG_OK,"
            )
        ):

            initial_config_seen = True

            print(
                "[CONFIG] Initial ESP32 "
                "configuration observed"
            )

            break


    # --------------------------------------------------------
    # BLE_READY should normally always be seen.
    #
    # Requiring initial CONFIG_OK as well ensures we are
    # definitely past setup() and inside loop(), where
    # handleSerial() is active.
    # --------------------------------------------------------

    if not ble_ready:

        raise RuntimeError(
            "BLE sender did not reach BLE_READY "
            "within 30 seconds"
        )


    if not initial_config_seen:

        raise RuntimeError(
            "BLE sender did not finish startup "
            "configuration within 30 seconds"
        )


    # ========================================================
    # STEP 2:
    # SEND THE ACTUAL EXPERIMENT CONFIGURATION
    # ========================================================

    command = (
        f"CONFIG,"
        f"{PAYLOAD_BYTES},"
        f"{PACKET_INTERVAL_MS}\n"
    )


    print(
        f"[CONFIG] Sent -> "
        f"payload={PAYLOAD_BYTES} bytes, "
        f"interval={PACKET_INTERVAL_MS} ms"
    )


    ser.write(
        command.encode(
            "utf-8"
        )
    )


    ser.flush()


    # ========================================================
    # STEP 3:
    # WAIT FOR CONFIRMATION OF THE COMMAND WE JUST SENT
    # ========================================================

    confirmation_timeout_at = (
        time.monotonic()
        + 5
    )


    while (
        time.monotonic()
        < confirmation_timeout_at
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
            "[ESP]",
            line
        )


        # ----------------------------------------------------
        # Expected:
        #
        # CONFIG_OK,16,100
        # ----------------------------------------------------

        if line.startswith(
            "CONFIG_OK,"
        ):

            parts = (
                line.split(",")
            )


            if (
                len(parts) != 3
            ):

                print(
                    "[WARN] Invalid BLE "
                    "CONFIG_OK format:"
                )

                print(
                    line
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

                print(
                    "[WARN] Invalid CONFIG_OK values:"
                )

                print(
                    line
                )

                continue


            # ------------------------------------------------
            # Verify payload
            # ------------------------------------------------

            if (
                confirmed_payload
                != PAYLOAD_BYTES
            ):

                raise RuntimeError(
                    "ESP32 payload confirmation mismatch: "
                    f"Python={PAYLOAD_BYTES}, "
                    f"ESP32={confirmed_payload}"
                )


            # ------------------------------------------------
            # Verify packet interval
            # ------------------------------------------------

            if (
                confirmed_interval
                != PACKET_INTERVAL_MS
            ):

                raise RuntimeError(
                    "ESP32 interval confirmation mismatch: "
                    f"Python={PACKET_INTERVAL_MS}, "
                    f"ESP32={confirmed_interval}"
                )


            print(
                "[CONFIG] Protocol: BLE"
            )


            print(
                f"[CONFIG] BLE PHY: "
                f"{BLE_PHY}"
            )


            print(
                "[CONFIG] ESP32 configuration confirmed"
            )


            return


        # ----------------------------------------------------
        # Configuration rejected
        # ----------------------------------------------------

        if line.startswith(
            "CONFIG_ERROR"
        ):

            raise RuntimeError(
                "ESP32 rejected configuration: "
                f"{line}"
            )


    raise RuntimeError(
        "ESP32 did not confirm the requested "
        "configuration within 5 seconds"
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

    timestamp_us: int


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
    Expected BLE sender format:

    PKT,
    packet_id,
    payload_bytes,
    rssi_dbm,
    rtt_ms,
    successful,
    retries,
    timestamp_us

    Example:

    PKT,42,16,-63,8.25,1,0,49381000
    """


    if not line.startswith(
        "PKT,"
    ):

        return None


    parts = (
        line.split(",")
    )


    if (
        len(parts) != 8
    ):

        print(
            f"[WARN] Expected 8 fields, "
            f"got {len(parts)}: "
            f"{line}"
        )


        return None


    try:

        # ----------------------------------------------------
        # Packet ID
        # ----------------------------------------------------

        packet_id = int(
            parts[1]
        )


        # ----------------------------------------------------
        # Payload size
        # ----------------------------------------------------

        payload_bytes = int(
            parts[2]
        )


        # ----------------------------------------------------
        # BLE RSSI
        #
        # BLE sender obtains this using:
        #
        # pClient->getRssi()
        #
        # -127 is treated as unavailable.
        # ----------------------------------------------------

        raw_rssi = float(
            parts[3]
        )


        rssi_dbm = (
            None
            if raw_rssi <= -127
            else raw_rssi
        )


        # ----------------------------------------------------
        # RTT
        #
        # Negative RTT means ACK was not received.
        # ----------------------------------------------------

        rtt_value = float(
            parts[4]
        )


        rtt_ms = (
            None
            if rtt_value < 0
            else rtt_value
        )


        # ----------------------------------------------------
        # Packet success
        # ----------------------------------------------------

        successful = bool(
            int(
                parts[5]
            )
        )


        # ----------------------------------------------------
        # Retry count
        #
        # Current BLE sender reports zero.
        # ----------------------------------------------------

        retries = int(
            parts[6]
        )


        # ----------------------------------------------------
        # ESP32 timestamp
        #
        # IMPORTANT:
        #
        # BLE sender uses micros(),
        # therefore this is microseconds.
        # ----------------------------------------------------

        timestamp_us = int(
            parts[7]
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

            timestamp_us=
                timestamp_us,
        )


    except ValueError as exc:

        print(
            f"[WARN] Parse error: "
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


    # --------------------------------------------------------
    # BLE packet must contain at least 4 bytes because
    # bytes 0 - 3 contain the sequence number.
    # --------------------------------------------------------

    if (
        PAYLOAD_BYTES < 4
    ):

        raise ValueError(
            "PAYLOAD_BYTES must be >= 4 "
            "for the BLE sender"
        )


    if (
        PAYLOAD_BYTES
        > MAX_PAYLOAD_BYTES
    ):

        raise ValueError(
            f"PAYLOAD_BYTES must be <= "
            f"{MAX_PAYLOAD_BYTES}"
        )


    if (
        PACKET_INTERVAL_MS < 10
    ):

        raise ValueError(
            "PACKET_INTERVAL_MS must be >= 10 "
            "for the current BLE sender"
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


    if not BLE_PHY:

        raise ValueError(
            "BLE_PHY cannot be null "
            "for BLE experiments"
        )


# ============================================================
#             PACKET CONFIGURATION VALIDATION
# ============================================================

def validate_packet_configuration(
    packet: PacketTelemetry,
) -> bool:

    # --------------------------------------------------------
    # Validate Python payload range
    # --------------------------------------------------------

    if not (
        4
        <= PAYLOAD_BYTES
        <= MAX_PAYLOAD_BYTES
    ):

        print()


        print(
            "[INVALID PYTHON CONFIGURATION]"
        )


        print(
            f"PAYLOAD_BYTES must be between "
            f"4 and {MAX_PAYLOAD_BYTES}"
        )


        print(
            f"Current PAYLOAD_BYTES : "
            f"{PAYLOAD_BYTES}"
        )


        print()


        return False


    # --------------------------------------------------------
    # Verify sender payload
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
            "The packet will NOT be "
            "added to the experiment."
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


    # --------------------------------------------------------
    # Validate payload consistency
    # --------------------------------------------------------

    actual_payload_sizes = {

        packet.payload_bytes

        for packet
        in packets
    }


    if (
        len(
            actual_payload_sizes
        )
        != 1
    ):

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
    # Application payload throughput
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
    #
    # Current BLE sender reports zero retries, but retaining
    # the field keeps the dataset/API schema identical.
    # --------------------------------------------------------

    total_retries = sum(

        packet.retries

        for packet
        in packets
    )


    # --------------------------------------------------------
    # Overall experiment success
    # --------------------------------------------------------

    successful = (
        packets_received > 0
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
        # Distance
        # ----------------------------------------------------

        "distance_m":
            DISTANCE_M,


        # ----------------------------------------------------
        # Environment
        # ----------------------------------------------------

        "environment":
            ENVIRONMENT,


        # ----------------------------------------------------
        # Visibility
        # ----------------------------------------------------

        "line_of_sight":
            LINE_OF_SIGHT,


        # ----------------------------------------------------
        # Obstacle
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
        # Payload
        # ----------------------------------------------------

        "payload_bytes":
            actual_payload_bytes,


        # ----------------------------------------------------
        # Packet interval
        # ----------------------------------------------------

        "packet_interval_ms":
            PACKET_INTERVAL_MS,


        # ----------------------------------------------------
        # Number of packets measured
        # ----------------------------------------------------

        "packet_count":
            packets_sent,


        # ----------------------------------------------------
        # Traffic requirement
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
        # Latency
        #
        # Individual BLE RTT values are aggregated into the
        # experiment latency statistics.
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
        # Experiment duration
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
        # Wi-Fi-specific
        #
        # Must be NULL for BLE.
        # ----------------------------------------------------

        "wifi_channel":
            WIFI_CHANNEL,


        # ----------------------------------------------------
        # BLE-specific
        # ----------------------------------------------------

        "ble_phy":
            BLE_PHY,


        # ----------------------------------------------------
        # Bluetooth Classic-specific
        #
        # Must be NULL for BLE.
        # ----------------------------------------------------

        "bt_mode":
            BT_MODE,


        # ----------------------------------------------------
        # LoRa-specific
        # ----------------------------------------------------

        "lora_sf":
            LORA_SF,


        "lora_bw":
            LORA_BW,


        "lora_cr":
            LORA_CR,


        # ----------------------------------------------------
        # Cellular-specific
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

    # --------------------------------------------------------
    # Ensure backup directory exists
    # --------------------------------------------------------

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
        f"BLE PHY              : "
        f"{BLE_PHY}"
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
        f"BLE PHY       : "
        f"{measurement['ble_phy']}"
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
        f"{measurement['transfer_time_ms'] / 1000:.2f} s"
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
    # Clear stale serial output
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


    print(
        f"[TEST] BLE PHY: "
        f"{BLE_PHY}"
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


        # ----------------------------------------------------
        # ESP32 debug / connection messages
        #
        # Examples:
        #
        # BLE_CONNECTED
        # BLE_SCANNING
        # BLE_TARGET_FOUND
        # BLE_READY
        # ----------------------------------------------------

        if not line.startswith(
            "PKT,"
        ):

            print(
                "[ESP]",
                line,
            )


            continue


        # ----------------------------------------------------
        # Parse PKT line
        # ----------------------------------------------------

        packet = (
            parse_packet_line(
                line
            )
        )


        if (
            packet is None
        ):

            continue


        # ----------------------------------------------------
        # Prevent wrongly labelled payload data
        # ----------------------------------------------------

        if not validate_packet_configuration(
            packet
        ):

            continue


        # ----------------------------------------------------
        # Store packet
        # ----------------------------------------------------

        window.add(
            packet
        )


        # ----------------------------------------------------
        # Human-readable status
        # ----------------------------------------------------

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


        print(
            f"[PKT] "
            f"id={packet.packet_id:<6d} "
            f"{status:<4s} "
            f"payload={packet.payload_bytes:<4d}B "
            f"RSSI={rssi_text:>9s} "
            f"RTT={rtt_text:>9s}"
        )


    window.stop()


    return window


# ============================================================
#                          MAIN
# ============================================================

def main(
) -> None:

    # --------------------------------------------------------
    # Validate experiment configuration
    # --------------------------------------------------------

    validate_configuration()


    # --------------------------------------------------------
    # Print experiment settings
    # --------------------------------------------------------

    print_experiment_configuration()


    # --------------------------------------------------------
    # Check API
    #
    # Experiment is still allowed to continue if API is down.
    # Failed measurements will be stored locally.
    # --------------------------------------------------------

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
                    1,

            ) as ser:


                # ------------------------------------------------
                # ESP32 may reset when serial port opens
                # ------------------------------------------------

                time.sleep(
                    2
                )


                print(
                    "[SERIAL] Connected"
                )


                # ------------------------------------------------
                # Configure BLE sender
                # ------------------------------------------------

                configure_esp32(
                    ser
                )


                # ------------------------------------------------
                # Remove remaining CONFIG / debug messages
                # ------------------------------------------------

                ser.reset_input_buffer()


                # ================================================
                # RUN ALL REPETITIONS
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


                    # --------------------------------------------
                    # No packets collected
                    # --------------------------------------------

                    if not window.packets:

                        print(
                            "[WARNING] No valid packets "
                            "collected during this repetition."
                        )


                        continue


                    # --------------------------------------------
                    # Build experiment measurement
                    # --------------------------------------------

                    measurement = (
                        build_measurement(

                            window,

                            repetition,
                        )
                    )


                    # --------------------------------------------
                    # Display summary
                    # --------------------------------------------

                    print_measurement_summary(

                        measurement,

                        repetition,
                    )


                    # --------------------------------------------
                    # Send to API
                    # --------------------------------------------

                    success = (
                        send_measurement(
                            measurement
                        )
                    )


                    # --------------------------------------------
                    # Local backup if API submission fails
                    # --------------------------------------------

                    if not success:

                        save_failed_measurement(
                            measurement
                        )


                    # --------------------------------------------
                    # Separate independent repetitions
                    # --------------------------------------------

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


# ============================================================
#                     PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()