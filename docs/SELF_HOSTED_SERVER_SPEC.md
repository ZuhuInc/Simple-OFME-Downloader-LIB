# Fanta-OFME-Cloud — Self-Hosted Server API Specification

Companion Server Repository: **[ReTr0777/Fanta-OFME-Cloud](https://github.com/ReTr0777/Fanta-OFME-Cloud)**

This document defines the exact HTTP REST API contract expected by **Fanta OFME Downloader** when the **Self-Hosted Cloud Server (`self_hosted`)** provider is selected.

---

## 1. Authentication

When the user configures an **API Key** in Fanta OFME Downloader, the client sends both headers on every request:
```http
Authorization: Bearer <api_key>
X-API-Key: <api_key>
```
- **Single-User / Personal Server**: Verify against an environment variable (e.g. `FANTA_API_KEY`). If `FANTA_API_KEY` is empty/unset on the server, allow unauthenticated requests (ideal for trusted LAN / Tailscale setups).
- **Multi-User / Friends Server**: Map each distinct API key (or hash of the API key) to its own isolated storage subdirectory (`data/saves/<key_hash>/`), so multiple friends can share one `Fanta-OFME-Cloud` instance without overwriting each other's saves.
- Return `401 Unauthorized` or `403 Forbidden` if an invalid key is provided.

---

## 2. Endpoints

### `GET /api/status`
Health check and authentication verification endpoint used by the **"Test Connection"** button in the client.

**Response (`200 OK`):**
```json
{
  "success": true,
  "status": "ok",
  "server_name": "Fanta-OFME-Cloud",
  "version": "1.0.0",
  "authenticated": true
}
```

---

### `GET /api/saves`
Lists all backed-up save archives in the active user's bucket so the client can pre-index and compare timestamps across the entire game library in a single request.

**Response (`200 OK`):**
```json
{
  "success": true,
  "saves": [
    {
      "safe_name": "Schedule I",
      "title": "Schedule I",
      "size_bytes": 1458291,
      "mtime": 1730541200.5,
      "updated_at": "2026-11-02T10:00:00Z"
    }
  ]
}
```

---

### `GET /api/saves/<safe_name>`
Returns metadata for a single game save archive. `<safe_name>` is URL-encoded (`urllib.parse.quote(safe_name)`).

**Response (`200 OK` when found):**
```json
{
  "exists": true,
  "safe_name": "Schedule I",
  "title": "Schedule I",
  "size_bytes": 1458291,
  "mtime": 1730541200.5
}
```
*(If no save exists for `<safe_name>`, return either `404 Not Found` or `200 OK` with `{"exists": false}`).*

---

### `POST /api/saves/<safe_name>`
Uploads a zipped game save archive.

**Request (`multipart/form-data`):**
- **File field `file`**: `<safe_name>_save.zip` (`application/zip`)
- **Form field `title`**: Full game title (e.g., `"Schedule I"`)
- **Form field `safe_name`**: Sanitized folder/archive key (e.g., `"Schedule I"`)
- **Form field `mtime`**: Float Unix timestamp of the local save's last modification time (e.g., `"1730541200.5"`). **Important:** Store this `mtime` in a sidecar `metadata.json` or database on the server and return it in `GET /api/saves` and `GET /api/saves/<safe_name>` so cross-PC timestamp comparison (`in_sync` vs `local_newer` vs `cloud_newer`) remains accurate to the second.

**Response (`200 OK` or `201 Created`):**
```json
{
  "success": true,
  "safe_name": "Schedule I",
  "size_bytes": 1458291,
  "mtime": 1730541200.5
}
```

---

### `GET /api/saves/<safe_name>/download`
Downloads the binary `.zip` save archive for extraction and restoration on the client PC.

**Response (`200 OK`):**
- `Content-Type: application/zip`
- Binary stream of `<safe_name>_save.zip`

---

### `DELETE /api/saves/<safe_name>`
Deletes the cloud save archive and its metadata for `<safe_name>` from the server.

**Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Deleted cloud backup for Schedule I"
}
```

