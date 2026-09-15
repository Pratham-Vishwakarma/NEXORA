"""FastAPI middleware for collecting adaptive-network experiments."""

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import timezone
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from .database import connection, initialise_database
from .models import IngestResult, MeasurementIn, MeasurementOut, Protocol


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialise_database()
    yield


app = FastAPI(
    title="Adaptive Network Data API",
    version="1.0.0",
    description=(
        "Stores comparable Wi-Fi, BLE, Bluetooth Classic, LoRa, "
        "4G, 5G, and Zigbee network test observations."
    ),
    lifespan=lifespan,
)


# MeasurementIn fields map directly to the SQLite table.
COLUMNS = list(MeasurementIn.model_fields)

INSERT_SQL = (
    f"INSERT INTO measurements ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in COLUMNS)})"
)


def normalise_protocol(value: str) -> str:
    """Normalise protocol aliases used in query parameters."""

    value = value.strip().upper()

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

        "LTE": "4G",
        "4G": "4G",

        "NR": "5G",
        "5G": "5G",

        "ZIGBEE": "ZIGBEE",
    }

    return aliases.get(value, value)


def serialise(measurement: MeasurementIn) -> tuple[object, ...]:
    """Convert a validated Pydantic model into SQLite-compatible values."""

    data = measurement.model_dump()

    data["timestamp"] = (
        data["timestamp"]
        .astimezone(timezone.utc)
        .isoformat()
    )

    return tuple(
        int(value) if isinstance(value, bool) else value
        for value in data.values()
    )


def row_to_response(row: dict) -> dict:
    """Convert SQLite values into API-friendly values."""

    row["line_of_sight"] = (
        bool(row["line_of_sight"])
        if row["line_of_sight"] is not None
        else None
    )

    row["successful"] = bool(row["successful"])

    return row


def store(measurements: list[MeasurementIn]) -> list[int]:
    """Store one or more measurements and return inserted IDs."""

    with connection() as conn:
        cursor = conn.cursor()

        ids: list[int] = []

        for measurement in measurements:
            cursor.execute(
                INSERT_SQL,
                serialise(measurement),
            )

            ids.append(cursor.lastrowid)

        return ids


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Adaptive Network Data API",
        "status": "Live",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/measurements",
    response_model=IngestResult,
    status_code=201,
)
def ingest_measurement(
    measurement: MeasurementIn,
) -> IngestResult:

    ids = store([measurement])

    return IngestResult(
        stored=1,
        ids=ids,
    )


@app.post(
    "/measurements/batch",
    response_model=IngestResult,
    status_code=201,
)
def ingest_batch(
    measurements: list[MeasurementIn] = Body(
        ...,
        min_length=1,
        max_length=1000,
    ),
) -> IngestResult:

    ids = store(measurements)

    return IngestResult(
        stored=len(ids),
        ids=ids,
    )


@app.get(
    "/measurements",
    response_model=list[MeasurementOut],
)
def list_measurements(
    protocol: str | None = Query(
        default=None,
        description=(
            "Filter by protocol: WIFI, BT, BLE, LORA, "
            "4G, 5G, or ZIGBEE. Aliases such as LTE and NR are supported."
        ),
    ),
    experiment_id: str | None = None,
    limit: Annotated[
        int,
        Query(ge=1, le=1000),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
) -> list[dict]:

    conditions: list[str] = []
    parameters: list[object] = []

    if protocol:
        protocol = normalise_protocol(protocol)

        valid_protocols = {
            "WIFI",
            "BT",
            "BLE",
            "LORA",
            "4G",
            "5G",
            "ZIGBEE",
        }

        if protocol not in valid_protocols:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid protocol. Allowed values: "
                    "WIFI, BT, BLE, LORA, 4G, 5G, ZIGBEE"
                ),
            )

        conditions.append("protocol = ?")
        parameters.append(protocol)

    if experiment_id:
        conditions.append("experiment_id = ?")
        parameters.append(experiment_id)

    where = (
        f" WHERE {' AND '.join(conditions)}"
        if conditions
        else ""
    )

    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM measurements
            {where}
            ORDER BY id DESC
            LIMIT ?
            OFFSET ?
            """,
            [
                *parameters,
                limit,
                offset,
            ],
        ).fetchall()

    return [
        row_to_response(dict(row))
        for row in rows
    ]


@app.get(
    "/measurements/{measurement_id}",
    response_model=MeasurementOut,
)
def get_measurement(
    measurement_id: int,
) -> dict:

    with connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM measurements
            WHERE id = ?
            """,
            (measurement_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Measurement not found",
        )

    return row_to_response(dict(row))


@app.get("/summary")
def summary() -> list[dict]:
    """Return aggregate performance metrics grouped by protocol."""

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT
                protocol,
                radio_family,
                cellular_generation,

                COUNT(*) AS observations,

                ROUND(
                    AVG(packet_loss_pct),
                    3
                ) AS avg_packet_loss_pct,

                ROUND(
                    AVG(latency_mean_ms),
                    3
                ) AS avg_latency_ms,

                ROUND(
                    AVG(throughput_kbps),
                    3
                ) AS avg_throughput_kbps,

                ROUND(
                    AVG(rssi_dbm),
                    3
                ) AS avg_rssi_dbm,

                ROUND(
                    AVG(snr_db),
                    3
                ) AS avg_snr_db,

                ROUND(
                    AVG(estimated_energy_mj),
                    3
                ) AS avg_energy_mj,

                ROUND(
                    100.0 * AVG(successful),
                    2
                ) AS success_pct

            FROM measurements

            GROUP BY
                protocol,
                radio_family,
                cellular_generation

            ORDER BY protocol
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


@app.get("/export.csv")
def export_csv() -> StreamingResponse:
    """Export all collected measurements as a CSV dataset."""

    with connection() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM measurements
                ORDER BY id
                """
            )
        ]

    stream = io.StringIO()

    writer = csv.DictWriter(
        stream,
        fieldnames=[
            "id",
            *COLUMNS,
            "received_at",
        ],
    )

    writer.writeheader()
    writer.writerows(rows)

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=adaptive_network_dataset.csv"
        },
    )
