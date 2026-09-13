"""SQLite setup and persistence helpers."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/adaptive_network.db"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    protocol TEXT NOT NULL,
    radio_family TEXT,
    source_node TEXT,
    destination_node TEXT,
    distance_m REAL,
    environment TEXT,
    line_of_sight INTEGER,
    obstacle_type TEXT,
    mobility TEXT,
    interference_level TEXT,
    payload_bytes INTEGER,
    packet_interval_ms INTEGER,
    packet_count INTEGER,
    traffic_type TEXT,
    qos_priority TEXT,
    required_latency_ms REAL,
    required_throughput_kbps REAL,
    reliability_requirement REAL,
    power_priority TEXT,
    range_requirement_m REAL,
    rssi_dbm REAL,
    snr_db REAL,
    link_quality REAL,
    tx_power_dbm REAL,
    packets_sent INTEGER,
    packets_received INTEGER,
    packets_lost INTEGER,
    packet_loss_pct REAL,
    rtt_ms REAL,
    latency_mean_ms REAL,
    latency_min_ms REAL,
    latency_max_ms REAL,
    jitter_ms REAL,
    throughput_kbps REAL,
    transfer_time_ms REAL,
    retries INTEGER,
    connection_setup_ms REAL,
    disconnect_count INTEGER,
    battery_voltage REAL,
    current_ma REAL,
    estimated_energy_mj REAL,
    wifi_channel INTEGER,
    ble_phy TEXT,
    bt_mode TEXT,
    lora_sf INTEGER,
    lora_bw INTEGER,
    lora_cr TEXT,
    cellular_generation TEXT,
    cell_signal_dbm REAL,
    successful INTEGER NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_measurements_experiment ON measurements(experiment_id);
CREATE INDEX IF NOT EXISTS idx_measurements_protocol ON measurements(protocol);
CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements(timestamp);
"""


def initialise_database() -> None:
    """Create the database directory, tables, and indexes if necessary."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.executescript(SCHEMA_SQL)


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
