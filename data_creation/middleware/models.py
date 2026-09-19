"""API contracts for protocol-agnostic link measurements."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Protocol = Literal[
    "WIFI",
    "BT",
    "BLE",
    "LORA",
    "4G",
    "5G",
    "ZIGBEE",
]


class MeasurementIn(BaseModel):
    """One aggregate observation from a controlled network test.

    Leave radio-specific fields unset when a protocol cannot expose them.
    Values are measured facts; the ML training label is created later.
    """

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    experiment_id: str = Field(min_length=1, max_length=100)
    protocol: Protocol

    radio_family: str | None = Field(default=None, max_length=50)

    source_node: str | None = Field(default=None, max_length=100)
    destination_node: str | None = Field(default=None, max_length=100)

    distance_m: float | None = Field(default=None, ge=0)
    environment: str | None = Field(default=None, max_length=50)
    line_of_sight: bool | None = None
    obstacle_type: str | None = Field(default=None, max_length=100)
    mobility: str | None = Field(default=None, max_length=50)
    interference_level: str | None = Field(default=None, max_length=50)

    payload_bytes: int | None = Field(default=None, ge=0)
    packet_interval_ms: int | None = Field(default=None, ge=0)
    packet_count: int | None = Field(default=None, ge=0)

    traffic_type: str | None = Field(default=None, max_length=50)
    qos_priority: str | None = Field(default=None, max_length=50)

    required_latency_ms: float | None = Field(default=None, ge=0)
    required_throughput_kbps: float | None = Field(default=None, ge=0)
    reliability_requirement: float | None = Field(
        default=None, ge=0, le=1
    )
    power_priority: str | None = Field(default=None, max_length=50)
    range_requirement_m: float | None = Field(default=None, ge=0)

    # Link measurements
    rssi_dbm: float | None = None
    snr_db: float | None = None
    link_quality: float | None = Field(default=None, ge=0)
    tx_power_dbm: float | None = None

    packets_sent: int | None = Field(default=None, ge=0)
    packets_received: int | None = Field(default=None, ge=0)
    packets_lost: int | None = Field(default=None, ge=0)
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100)

    rtt_ms: float | None = Field(default=None, ge=0)
    latency_mean_ms: float | None = Field(default=None, ge=0)
    latency_min_ms: float | None = Field(default=None, ge=0)
    latency_max_ms: float | None = Field(default=None, ge=0)
    jitter_ms: float | None = Field(default=None, ge=0)

    throughput_kbps: float | None = Field(default=None, ge=0)
    transfer_time_ms: float | None = Field(default=None, ge=0)

    retries: int | None = Field(default=None, ge=0)
    connection_setup_ms: float | None = Field(default=None, ge=0)
    disconnect_count: int | None = Field(default=None, ge=0)

    battery_voltage: float | None = Field(default=None, ge=0)
    current_ma: float | None = Field(default=None, ge=0)
    estimated_energy_mj: float | None = Field(default=None, ge=0)

    # ---------------------------------------------------------
    # Protocol-specific fields
    # ---------------------------------------------------------

    # Wi-Fi
    wifi_channel: int | None = Field(
        default=None,
        ge=1,
        le=196,
    )

    # BLE
    ble_phy: str | None = Field(
        default=None,
        max_length=50,
    )

    # Bluetooth Classic
    bt_mode: str | None = Field(
        default=None,
        max_length=50,
    )

    # LoRa
    lora_sf: int | None = Field(
        default=None,
        ge=5,
        le=12,
    )
    lora_bw: int | None = Field(
        default=None,
        gt=0,
    )
    lora_cr: str | None = Field(
        default=None,
        max_length=50,
    )

    # Cellular
    cellular_generation: Literal["4G", "5G"] | None = None
    cell_signal_dbm: float | None = None

    successful: bool

    # ---------------------------------------------------------
    # Protocol normalization
    # ---------------------------------------------------------

    @field_validator("protocol", mode="before")
    @classmethod
    def normalise_protocol(cls, value: str) -> str:
        value = str(value).strip().upper()

        aliases = {
            "WI-FI": "WIFI",
            "WIFI": "WIFI",

            "BLUETOOTH": "BT",
            "BLUETOOTH_CLASSIC": "BT",
            "BLUETOOTH CLASSIC": "BT",

            "BT": "BT",

            "BLUETOOTH_LOW_ENERGY": "BLE",
            "BLUETOOTH LOW ENERGY": "BLE",
            "BLE": "BLE",

            "LORA": "LORA",
            "LO-RA": "LORA",

            "4G": "4G",
            "LTE": "4G",

            "5G": "5G",
            "NR": "5G",

            "ZIGBEE": "ZIGBEE",
        }

        return aliases.get(value, value)

    # ---------------------------------------------------------
    # Protocol-specific automatic updates
    # ---------------------------------------------------------

    @model_validator(mode="after")
    def configure_protocol_fields(self) -> "MeasurementIn":

        if self.protocol == "WIFI":
            self.radio_family = "WIFI"

            # Remove fields belonging to other protocols
            self.ble_phy = None
            self.bt_mode = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

            self.cellular_generation = None
            self.cell_signal_dbm = None

        elif self.protocol == "BLE":
            self.radio_family = "BLUETOOTH"

            self.wifi_channel = None
            self.bt_mode = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

            self.cellular_generation = None
            self.cell_signal_dbm = None

        elif self.protocol == "BT":
            self.radio_family = "BLUETOOTH"

            self.wifi_channel = None
            self.ble_phy = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

            self.cellular_generation = None
            self.cell_signal_dbm = None

        elif self.protocol == "LORA":
            self.radio_family = "LORA"

            self.wifi_channel = None
            self.ble_phy = None
            self.bt_mode = None

            self.cellular_generation = None
            self.cell_signal_dbm = None

        elif self.protocol == "4G":
            self.radio_family = "CELLULAR"
            self.cellular_generation = "4G"

            self.wifi_channel = None
            self.ble_phy = None
            self.bt_mode = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

        elif self.protocol == "5G":
            self.radio_family = "CELLULAR"
            self.cellular_generation = "5G"

            self.wifi_channel = None
            self.ble_phy = None
            self.bt_mode = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

        elif self.protocol == "ZIGBEE":
            self.radio_family = "ZIGBEE"

            self.wifi_channel = None
            self.ble_phy = None
            self.bt_mode = None

            self.lora_sf = None
            self.lora_bw = None
            self.lora_cr = None

            self.cellular_generation = None
            self.cell_signal_dbm = None

        return self

    # ---------------------------------------------------------
    # Packet validation
    # ---------------------------------------------------------

    @model_validator(mode="after")
    def validate_packet_counts(self) -> "MeasurementIn":
        if (
            self.packets_sent is not None
            and self.packets_received is not None
        ):
            if self.packets_received > self.packets_sent:
                raise ValueError(
                    "packets_received cannot exceed packets_sent"
                )

        return self


class IngestResult(BaseModel):
    stored: int
    ids: list[int]


class MeasurementOut(MeasurementIn):
    id: int
    received_at: datetime
