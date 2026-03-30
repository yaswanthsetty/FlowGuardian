# IoT Handoff: Traffic Cloud API Contract

## Purpose
This document is for firmware/IoT integration.

Flow:
1. ML system posts traffic updates to `POST /update`.
2. IoT device polls `GET /get` to fetch the latest compact decision.

Base URL example:
- `http://<server-ip>:3000`

## Endpoints

### 1) Health Check
- Method: `GET`
- Path: `/`
- Success response: plain text `Traffic Server Running`

### 2) Update from ML
- Method: `POST`
- Path: `/update`
- Content-Type: `application/json`
- Success response: `200 Updated`
- Error responses:
  - `400 Invalid JSON format`
  - `500 Server Error`

### 3) IoT Polling Endpoint
- Method: `GET`
- Path: `/get`
- Returns latest compact decision JSON.

### 4) Debug Endpoint (optional)
- Method: `GET`
- Path: `/latest`
- Returns:
  - current compact `decision`
  - last full payload from ML (`latestSignalPayload`)

## Compact Decision Schema (`GET /get`)
```json
{
  "green": "A",
  "lane": 1,
  "duration": 5,
  "mode": "NORMAL",
  "reason": "default",
  "updatedAt": "2026-03-30T10:20:30.123Z"
}
```

Field meanings:
- `green`: lane symbol for device logic (`A`, `B`, `C`, ...)
- `lane`: numeric lane id
- `duration`: green time in seconds
- `mode`: scheduler mode (`NORMAL` or `OVERRIDE`)
- `reason`: mode reason (`default`, `density`, `ambulance`)
- `updatedAt`: ISO timestamp when decision was updated

## Accepted Payloads for `POST /update`

### A) Cycle mode payload (from ML app)
```json
{
  "mode": "OVERRIDE",
  "reason": "density",
  "lanes": [
    {"lane": 2, "green": 28, "yellow": 5, "vehicle_count": 15},
    {"lane": 1, "green": 22, "yellow": 5, "vehicle_count": 11}
  ],
  "ambulance": {"active": false, "lane": null},
  "accident": {"active": false, "lane": null, "confidence": 0.0},
  "timestamp": "2026-03-30T10:20:30.123456+00:00"
}
```

Behavior:
- Server picks first lane in `lanes` as active output decision.
- `duration` is set from that lane's `green`.

### B) Interval mode payload (from ML app)
```json
{
  "mode": "OVERRIDE",
  "reason": "ambulance",
  "active_lane": 2,
  "green": 5,
  "ambulance": {"active": true, "lane": 2},
  "accident": {"active": false, "lane": null, "confidence": 0.0},
  "timestamp": "2026-03-30T10:20:30.123456+00:00"
}
```

Behavior:
- Server uses `active_lane` and `green` directly.

### C) Manual test payload
```json
{
  "green": "B",
  "lane": 2,
  "duration": 5,
  "mode": "MANUAL",
  "reason": "manual"
}
```

## Polling Guidance for Firmware
- Poll `GET /get` every 1 to 2 seconds.
- If `updatedAt` is unchanged, keep current light state.
- If changed, apply new `green` for `duration` seconds.
- Keep a local safety fallback (e.g., all-red) when server is unreachable.

## cURL Examples

### Post cycle payload
```bash
curl -X POST http://localhost:3000/update \
  -H "Content-Type: application/json" \
  -d '{"mode":"NORMAL","reason":"default","lanes":[{"lane":1,"green":20,"yellow":5,"vehicle_count":3}],"ambulance":{"active":false,"lane":null},"accident":{"active":false,"lane":null,"confidence":0.0},"timestamp":"2026-03-30T10:20:30.123456+00:00"}'
```

### Post interval payload
```bash
curl -X POST http://localhost:3000/update \
  -H "Content-Type: application/json" \
  -d '{"mode":"OVERRIDE","reason":"ambulance","active_lane":2,"green":5,"ambulance":{"active":true,"lane":2},"accident":{"active":false,"lane":null,"confidence":0.0},"timestamp":"2026-03-30T10:20:30.123456+00:00"}'
```

### Poll decision
```bash
curl http://localhost:3000/get
```

## Notes
- This contract is backward-safe for both cycle and interval control modes.
- Raspberry Pi control path remains separate and optional in the Python project.
- IoT should integrate against `/get` and not depend on internal ML fields.
