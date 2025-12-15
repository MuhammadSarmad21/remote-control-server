# Remote Control Server

This project exposes a Flask-based control server with a built-in web dashboard to monitor connected clients and execute remote actions.

## Features

- Real-time dashboard that lists every connected client with hostname, username, and platform metadata.
- Action buttons per client:
  - `System Info` — shows OS and runtime details.
  - `Browse` — lists directory contents for a supplied path.
  - `Command` — runs an arbitrary shell command.
- Responses are rendered inside stacked panels so you can keep an audit of previous operations.
- WebSocket protocol so dashboards stay in sync with client joins, disconnects, and responses.
- Sample Python client that demonstrates the JSON protocol.

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
flask --app server.app run --debug --port 8000
```

Open a browser at http://127.0.0.1:8000 to use the GUI dashboard.

### Running a sample client

```bash
cd clients
python sample_client.py
```

The client expects the server to be reachable at `ws://127.0.0.1:8000/ws/client`. Override with `SERVER_URL` if needed.

## Protocol

1. **Client handshake** — First WebSocket message must be:

```json
{
  "type": "hello",
  "client_id": "optional-custom-id",
  "hostname": "device-name",
  "username": "current-user",
  "platform": "Windows-10",
  "ip": "10.0.0.5"
}
```

2. **Server actions** — When an operator clicks a button, the server sends:

```json
{
  "type": "action",
  "action_id": "generated",
  "action_type": "system_info | list_dir | run_command",
  "args": {}
}
```

3. **Client responses** — Clients must answer with:

```json
{
  "type": "response",
  "action_id": "same-as-request",
  "action_type": "system_info",
  "success": true,
  "body": {}
}
```

Responses appear instantly in the dashboard panels.

## File Layout

- `server/app.py` — Flask app, connection hub, HTTP routes, and WebSocket handlers (via Flask-Sock).
- `server/dashboard/*` — Static dashboard assets.
- `clients/sample_client.py` — Simple asyncio client implementing the action protocol.
- `requirements.txt` — Python dependencies.

Feel free to extend the allowed action list or enrich the metadata that clients provide during the handshake. Update the dashboard buttons plus backend validation (`ALLOWED_ACTIONS`) at the same time.

