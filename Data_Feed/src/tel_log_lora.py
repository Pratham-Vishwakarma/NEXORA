import time
import json
import serial
import requests
from datetime import datetime, timezone


# ============================================================
# API CONFIGURATION
# ============================================================

API_BASE_URL = "http://100.72.37.28:8000"

HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
TELEMETRY_ENDPOINT = f"{API_BASE_URL}/telemetry"


# ============================================================
# SERIAL CONFIGURATION
# ============================================================

SERIAL_PORT = "COM8"
BAUD_RATE = 115200
SERIAL_TIMEOUT = 1.0


# ============================================================
# EXPERIMENT CONFIGURATION
# ============================================================

PROTOCOL = "LORA"
RADIO_FAMILY = "LPWAN"

# ------------------------------------------------------------
# LoRa radio configuration
#
# MUST match the Arduino sketches
# ------------------------------------------------------------

LORA_FREQUENCY_MHZ = 433.0
LORA_SPREADING_FACTOR = 7
LORA_BANDWIDTH_KHZ = 125.0
LORA_CODING_RATE = "4/5"
LORA_TX_POWER_DBM = 17

# ------------------------------------------------------------
# Physical test conditions
# ------------------------------------------------------------

DISTANCE_M = 0.0

PAYLOAD_SIZE_BYTES = 16
PACKET_INTERVAL_MS = 500

ENVIRONMENT = "INDOOR"

VISIBILITY = "LOS"

OBSTACLE = "NONE"

TRAFFIC_REQUIREMENT = "TELEMETRY"

# ------------------------------------------------------------
# Test execution
# ------------------------------------------------------------

TEST_DURATION_SECONDS = 20

REPETITIONS = 1


# ============================================================
# OPTIONAL BATTERY / ENERGY CONFIGURATION
# ============================================================

BATTERY_VOLTAGE = None
CURRENT_MA = None
ESTIMATED_ENERGY_MJ = None


# ============================================================
# PRINT EXPERIMENT CONFIGURATION
# ============================================================

def print_experiment_config():

    print()
    print("=" * 68)
    print("ADAPTIVE IoT NETWORK EXPERIMENT")
    print("=" * 68)

    print(f"Protocol             : {PROTOCOL}")
    print(f"Radio family         : {RADIO_FAMILY}")

    print(
        f"LoRa frequency       : "
        f"{LORA_FREQUENCY_MHZ:.1f} MHz"
    )

    print(
        f"Spreading factor     : "
        f"SF{LORA_SPREADING_FACTOR}"
    )

    print(
        f"Bandwidth            : "
        f"{LORA_BANDWIDTH_KHZ:.0f} kHz"
    )

    print(
        f"Coding rate          : "
        f"{LORA_CODING_RATE}"
    )

    print(
        f"TX power             : "
        f"{LORA_TX_POWER_DBM} dBm"
    )

    print(
        f"Distance             : "
        f"{DISTANCE_M:.1f} m"
    )

    print(
        f"Payload              : "
        f"{PAYLOAD_SIZE_BYTES} bytes"
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
        f"Visibility           : "
        f"{VISIBILITY}"
    )

    print(
        f"Obstacle             : "
        f"{OBSTACLE}"
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
# API HEALTH CHECK
# ============================================================

def check_api():

    try:

        response = requests.get(
            HEALTH_ENDPOINT,
            timeout=3
        )

        response.raise_for_status()

        print(
            f"[API] API reachable: "
            f"{response.status_code}"
        )

        return True

    except requests.RequestException as exc:

        print(
            f"[API] Cannot reach API: {exc}"
        )

        return False


# ============================================================
# OPEN SERIAL PORT
# ============================================================

def open_serial():

    try:

        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=SERIAL_TIMEOUT
        )

        time.sleep(2)

        ser.reset_input_buffer()

        print(
            f"[SERIAL] Connected to "
            f"{SERIAL_PORT} @ {BAUD_RATE}"
        )

        return ser

    except serial.SerialException as exc:

        print(
            f"[SERIAL] Failed to open port: {exc}"
        )

        return None


# ============================================================
# SEND ARDUINO CONFIGURATION
# ============================================================

def configure_sender(ser):

    print()
    print("[SERIAL] Configuring LoRa sender...")

    size_command = (
        f"SIZE,{PAYLOAD_SIZE_BYTES}\n"
    )

    interval_command = (
        f"INTERVAL,{PACKET_INTERVAL_MS}\n"
    )

    ser.write(
        size_command.encode("utf-8")
    )

    time.sleep(0.2)

    ser.write(
        interval_command.encode("utf-8")
    )

    time.sleep(0.5)

    ser.reset_input_buffer()


# ============================================================
# PARSE LORA PACKET
# ============================================================

def parse_lora_packet(line):

    """

    Expected Arduino serial format:

    PKT,
    packet_id,
    payload_size,
    rssi,
    snr,
    rtt_ms,
    success,
    timestamp

    Example:

    PKT,21,16,-37,10.25,76.41,1,12844

    """

    if not line.startswith("PKT,"):

        return None

    parts = line.split(",")

    if len(parts) != 8:

        return None

    try:

        packet = {

            "packet_id":
                int(parts[1]),

            "payload_size":
                int(parts[2]),

            "rssi":
                int(parts[3]),

            "snr":
                float(parts[4]),

            "rtt_ms":
                float(parts[5]),

            "success":
                int(parts[6]),

            "device_timestamp_ms":
                int(parts[7]),
        }

        return packet

    except ValueError:

        return None


# ============================================================
# BUILD API RECORD
# ============================================================

def build_api_payload(packet, repetition):

    success = packet["success"] == 1

    rtt_ms = packet["rtt_ms"]

    if not success or rtt_ms < 0:

        rtt_value = None

    else:

        rtt_value = rtt_ms

    if success:

        packet_loss = 0

    else:

        packet_loss = 1

    record = {

        # ----------------------------------------------------
        # General identification
        # ----------------------------------------------------

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "protocol":
            PROTOCOL,

        "radio_family":
            RADIO_FAMILY,

        # ----------------------------------------------------
        # LoRa configuration
        # ----------------------------------------------------

        "lora_frequency_mhz":
            LORA_FREQUENCY_MHZ,

        "lora_spreading_factor":
            LORA_SPREADING_FACTOR,

        "lora_bandwidth_khz":
            LORA_BANDWIDTH_KHZ,

        "lora_coding_rate":
            LORA_CODING_RATE,

        "lora_tx_power_dbm":
            LORA_TX_POWER_DBM,

        # ----------------------------------------------------
        # Experiment conditions
        # ----------------------------------------------------

        "distance_m":
            DISTANCE_M,

        "environment":
            ENVIRONMENT,

        "visibility":
            VISIBILITY,

        "obstacle":
            OBSTACLE,

        "traffic_requirement":
            TRAFFIC_REQUIREMENT,

        # ----------------------------------------------------
        # Packet configuration
        # ----------------------------------------------------

        "packet_id":
            packet["packet_id"],

        "payload_size":
            packet["payload_size"],

        "packet_interval_ms":
            PACKET_INTERVAL_MS,

        # ----------------------------------------------------
        # Radio metrics
        # ----------------------------------------------------

        "rssi":
            packet["rssi"],

        "snr":
            packet["snr"],

        # ----------------------------------------------------
        # Performance metrics
        # ----------------------------------------------------

        "rtt_ms":
            rtt_value,

        "success":
            success,

        "packet_loss":
            packet_loss,

        # ----------------------------------------------------
        # Energy fields
        # ----------------------------------------------------

        "battery_voltage":
            BATTERY_VOLTAGE,

        "current_ma":
            CURRENT_MA,

        "estimated_energy_mj":
            ESTIMATED_ENERGY_MJ,

        # ----------------------------------------------------
        # Miscellaneous
        # ----------------------------------------------------

        "repetition":
            repetition,

        "device_timestamp_ms":
            packet["device_timestamp_ms"],
    }

    return record


# ============================================================
# SEND RECORD TO API
# ============================================================

def send_to_api(record):

    try:

        response = requests.post(
            TELEMETRY_ENDPOINT,
            json=record,
            timeout=5
        )

        response.raise_for_status()

        return True

    except requests.RequestException as exc:

        print(
            f"[API] POST failed: {exc}"
        )

        return False


# ============================================================
# PRINT PACKET
# ============================================================

def print_packet(packet, api_success):

    success = packet["success"] == 1

    if success:

        state = "OK"

        rtt_text = (
            f"{packet['rtt_ms']:.2f}"
        )

    else:

        state = "LOST"

        rtt_text = "N/A"

    api_text = (
        "OK"
        if api_success
        else "FAIL"
    )

    print(
        f"[PKT] "
        f"id={packet['packet_id']:<6} "
        f"size={packet['payload_size']:<4} "
        f"RSSI={packet['rssi']:<5} "
        f"SNR={packet['snr']:<6.2f} "
        f"RTT={rtt_text:<8} "
        f"{state:<5} "
        f"API={api_text}"
    )


# ============================================================
# RUN ONE EXPERIMENT
# ============================================================

def run_experiment(
    ser,
    repetition,
    api_available
):

    print()
    print(
        f"[TEST] Starting repetition "
        f"{repetition}/{REPETITIONS}"
    )

    print("-" * 68)

    start_time = time.monotonic()

    packets_seen = 0
    packets_successful = 0
    packets_failed = 0

    rtt_values = []

    while (
        time.monotonic() - start_time <
        TEST_DURATION_SECONDS
    ):

        try:

            raw_line = ser.readline()

            if not raw_line:

                continue

            line = raw_line.decode(
                "utf-8",
                errors="replace"
            ).strip()

        except serial.SerialException as exc:

            print(
                f"[SERIAL] Read error: {exc}"
            )

            break

        if not line:

            continue

        # ----------------------------------------------------
        # Print useful Arduino messages
        # ----------------------------------------------------

        if (
            line.startswith("LORA_")
            or
            line.startswith("CONFIG_")
        ):

            print(
                f"[ESP] {line}"
            )

            continue

        # ----------------------------------------------------
        # Parse telemetry packet
        # ----------------------------------------------------

        packet = parse_lora_packet(
            line
        )

        if packet is None:

            print(
                f"[ESP] {line}"
            )

            continue

        packets_seen += 1

        if packet["success"] == 1:

            packets_successful += 1

            if packet["rtt_ms"] >= 0:

                rtt_values.append(
                    packet["rtt_ms"]
                )

        else:

            packets_failed += 1

        # ----------------------------------------------------
        # Build API object
        # ----------------------------------------------------

        record = build_api_payload(
            packet,
            repetition
        )

        # ----------------------------------------------------
        # Send to API
        # ----------------------------------------------------

        api_success = False

        if api_available:

            api_success = send_to_api(
                record
            )

        print_packet(
            packet,
            api_success
        )

    # ========================================================
    # EXPERIMENT SUMMARY
    # ========================================================

    print("-" * 68)

    if packets_seen > 0:

        success_rate = (
            packets_successful
            / packets_seen
            * 100.0
        )

        loss_rate = (
            packets_failed
            / packets_seen
            * 100.0
        )

    else:

        success_rate = 0.0
        loss_rate = 0.0

    if rtt_values:

        avg_rtt = (
            sum(rtt_values)
            / len(rtt_values)
        )

        min_rtt = min(
            rtt_values
        )

        max_rtt = max(
            rtt_values
        )

    else:

        avg_rtt = None
        min_rtt = None
        max_rtt = None

    print(
        f"[SUMMARY] Packets       : "
        f"{packets_seen}"
    )

    print(
        f"[SUMMARY] Successful    : "
        f"{packets_successful}"
    )

    print(
        f"[SUMMARY] Failed        : "
        f"{packets_failed}"
    )

    print(
        f"[SUMMARY] Success rate  : "
        f"{success_rate:.2f}%"
    )

    print(
        f"[SUMMARY] Packet loss   : "
        f"{loss_rate:.2f}%"
    )

    if avg_rtt is not None:

        print(
            f"[SUMMARY] Avg RTT       : "
            f"{avg_rtt:.2f} ms"
        )

        print(
            f"[SUMMARY] Min RTT       : "
            f"{min_rtt:.2f} ms"
        )

        print(
            f"[SUMMARY] Max RTT       : "
            f"{max_rtt:.2f} ms"
        )

    else:

        print(
            "[SUMMARY] RTT           : "
            "No successful packets"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print_experiment_config()

    api_available = check_api()

    ser = open_serial()

    if ser is None:

        return

    try:

        configure_sender(
            ser
        )

        for repetition in range(
            1,
            REPETITIONS + 1
        ):

            run_experiment(
                ser,
                repetition,
                api_available
            )

            if (
                repetition <
                REPETITIONS
            ):

                print()
                print(
                    "[TEST] Waiting before "
                    "next repetition..."
                )

                time.sleep(2)

    except KeyboardInterrupt:

        print()
        print(
            "[TEST] Interrupted by user."
        )

    finally:

        if ser.is_open:

            ser.close()

            print(
                "[SERIAL] Port closed."
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()