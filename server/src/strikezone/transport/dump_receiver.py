"""TCP dump receiver server module conforming to docs/protocol.md v2."""
import os
from pathlib import Path
import socket
import struct
import time
from typing import Dict, Any, Optional, Tuple


class DumpReceiver:
    """TCP server that sends DUMP commands and receives streamed MP4 clips from the mobile app."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9999):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.client_address: Optional[Tuple[str, int]] = None

    def start_server(self):
        """Bind and listen for incoming connections from the phone."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)

    def wait_for_client(self, timeout: Optional[float] = None) -> Tuple[str, int]:
        """Wait for the mobile app to connect."""
        if not self.server_socket:
            raise RuntimeError("Server socket is not started. Call start_server() first.")

        self.server_socket.settimeout(timeout)
        self.client_socket, self.client_address = self.server_socket.accept()
        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return self.client_address

    def send_dump_command(self, duration_seconds: float = 4.5):
        """Send the ASCII DUMP trigger command to the phone."""
        if not self.client_socket:
            raise RuntimeError("No client connected.")

        command = f"DUMP {duration_seconds:.1f}\n".encode("ascii")
        self.client_socket.sendall(command)

    def receive_mp4_payload(self, output_path: Path, timeout: float = 5.0) -> Dict[str, Any]:
        """Receive the 4-byte Big-Endian length header followed by the raw MP4 payload."""
        if not self.client_socket:
            raise RuntimeError("No client connected.")

        self.client_socket.settimeout(timeout)
        start_time = time.perf_counter()

        # 1. 4-byte header: Payload length (Big-Endian 32-bit unsigned int)
        header_bytes = self._read_exact(4)
        if not header_bytes:
            raise ConnectionError("Client disconnected before sending payload length header.")

        payload_length = struct.unpack("!I", header_bytes)[0]
        if payload_length <= 0:
            raise ValueError(f"Invalid payload length: {payload_length}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Receive exactly payload_length bytes and stream to disk
        bytes_received = 0
        chunk_size = 64 * 1024

        with open(output_path, "wb") as f:
            while bytes_received < payload_length:
                to_read = min(chunk_size, payload_length - bytes_received)
                chunk = self.client_socket.recv(to_read)
                if not chunk:
                    raise ConnectionError(
                        f"Connection lost while reading payload. Expected {payload_length} bytes, got {bytes_received}."
                    )
                f.write(chunk)
                bytes_received += len(chunk)

        elapsed_time = time.perf_counter() - start_time
        speed_mb_s = (bytes_received / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0.0

        return {
            "output_path": str(output_path),
            "payload_length": bytes_received,
            "elapsed_seconds": round(elapsed_time, 4),
            "transfer_speed_mb_s": round(speed_mb_s, 2),
        }

    def _read_exact(self, num_bytes: int) -> bytes:
        """Helper to read exactly num_bytes from the client socket."""
        data = bytearray()
        while len(data) < num_bytes:
            packet = self.client_socket.recv(num_bytes - len(data))
            if not packet:
                break
            data.extend(packet)
        return bytes(data)

    def close_client(self):
        """Close current client connection while keeping the server socket alive."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
            self.client_socket = None
            self.client_address = None

    def close(self):
        """Close both client and server sockets."""
        self.close_client()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None


def verify_mp4_integrity(file_path: Path) -> Dict[str, Any]:
    """Verify video file readability and decode the first frame to ensure no decoder smearing."""
    result = {
        "valid": False,
        "width": None,
        "height": None,
        "fps": None,
        "frame_count": None,
        "first_frame_decoded": False,
        "error": None,
    }

    if not file_path.is_file() or file_path.stat().st_size == 0:
        result["error"] = "File does not exist or is empty"
        return result

    try:
        import cv2

        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            result["error"] = "cv2.VideoCapture failed to open the file"
            return result

        result["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        result["fps"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
        result["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Check first frame decode (tests whether starting frame is a clean Key Frame)
        ok, frame = cap.read()
        cap.release()

        if ok and frame is not None and frame.size > 0:
            result["first_frame_decoded"] = True
            result["valid"] = True
        else:
            result["error"] = "Failed to decode the first frame"

    except ImportError:
        # Fallback if cv2 is not installed in the current environment: check MP4 box signature
        with open(file_path, "rb") as f:
            header = f.read(12)
            if len(header) >= 8 and b"ftyp" in header:
                result["valid"] = True
                result["error"] = "OpenCV not installed; checked MP4 ftyp container header only"
            else:
                result["error"] = "Missing MP4 ftyp container signature"

    except Exception as exc:
        result["error"] = str(exc)

    return result
