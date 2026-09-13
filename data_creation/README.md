# Adaptive Network Data API

SQLite-backed middleware for collecting comparable network-test records from ESP32 nodes, laptop test scripts, and cellular experiments. It deliberately accepts nullable radio-specific fields; do not fabricate unavailable readings.

## Run

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The database is created at `data/adaptive_network.db`. Override this location with `DATABASE_PATH` when needed. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Main endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /measurements` | Store one aggregate observation. |
| `POST /measurements/batch` | Store 1–1000 observations in one request. |
| `GET /measurements` | Filter records by `protocol` or `experiment_id`. |
| `GET /summary` | Per-protocol quality overview. |
| `GET /export.csv` | Download the ML-ready master dataset. |

## Example

```powershell
$row = @{
  experiment_id = 'wifi-indoor-001'
  protocol = 'WIFI'
  source_node = 'esp32-a'
  destination_node = 'esp32-b'
  distance_m = 5
  environment = 'indoor'
  line_of_sight = $true
  payload_bytes = 128
  packet_count = 100
  rssi_dbm = -62
  packets_sent = 100
  packets_received = 98
  packets_lost = 2
  packet_loss_pct = 2
  latency_mean_ms = 18.7
  jitter_ms = 2.4
  throughput_kbps = 540
  wifi_channel = 6
  successful = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/measurements -ContentType 'application/json' -Body $row
```

For an ESP32, POST the same JSON using `HTTPClient` after each completed test window (not after every packet). This keeps the database useful for ML without filling it with near-identical packet rows.
