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
    description="Stores comparable Wi-Fi, BLE, Bluetooth, LoRa, and cellular test observations.",
    lifespan=lifespan,
)

COLUMNS = list(MeasurementIn.model_fields)
INSERT_SQL = f"INSERT INTO measurements ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})"


def serialise(measurement: MeasurementIn) -> tuple[object, ...]:
    data = measurement.model_dump()
    data["timestamp"] = data["timestamp"].astimezone(timezone.utc).isoformat()
    return tuple(int(value) if isinstance(value, bool) else value for value in data.values())


def row_to_response(row: dict) -> dict:
    row["line_of_sight"] = bool(row["line_of_sight"]) if row["line_of_sight"] is not None else None
    row["successful"] = bool(row["successful"])
    return row


def store(measurements: list[MeasurementIn]) -> list[int]:
    with connection() as conn:
        cursor = conn.cursor()
        ids: list[int] = []
        for measurement in measurements:
            cursor.execute(INSERT_SQL, serialise(measurement))
            ids.append(cursor.lastrowid)
        return ids

@app.get("/")
def health() -> dict[str, str]:
    return {"message": "Live"}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/measurements", response_model=IngestResult, status_code=201)
def ingest_measurement(measurement: MeasurementIn) -> IngestResult:
    ids = store([measurement])
    return IngestResult(stored=1, ids=ids)


@app.post("/measurements/batch", response_model=IngestResult, status_code=201)
def ingest_batch(measurements: list[MeasurementIn] = Body(..., min_length=1, max_length=1000)) -> IngestResult:
    ids = store(measurements)
    return IngestResult(stored=len(ids), ids=ids)


@app.get("/measurements", response_model=list[MeasurementOut])
def list_measurements(
    protocol: Protocol | None = None,
    experiment_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    conditions: list[str] = []
    parameters: list[object] = []
    if protocol:
        conditions.append("protocol = ?")
        parameters.append(protocol)
    if experiment_id:
        conditions.append("experiment_id = ?")
        parameters.append(experiment_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM measurements{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
    return [row_to_response(dict(row)) for row in rows]


@app.get("/measurements/{measurement_id}", response_model=MeasurementOut)
def get_measurement(measurement_id: int) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM measurements WHERE id = ?", (measurement_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return row_to_response(dict(row))


@app.get("/summary")
def summary() -> list[dict]:
    with connection() as conn:
        rows = conn.execute("""
            SELECT protocol, COUNT(*) AS observations,
                   ROUND(AVG(packet_loss_pct), 3) AS avg_packet_loss_pct,
                   ROUND(AVG(latency_mean_ms), 3) AS avg_latency_ms,
                   ROUND(AVG(throughput_kbps), 3) AS avg_throughput_kbps,
                   ROUND(100.0 * AVG(successful), 2) AS success_pct
            FROM measurements GROUP BY protocol ORDER BY protocol
        """).fetchall()
    return [dict(row) for row in rows]


@app.get("/export.csv")
def export_csv() -> StreamingResponse:
    with connection() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM measurements ORDER BY id")]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["id", *COLUMNS, "received_at"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=adaptive_network_dataset.csv"})
