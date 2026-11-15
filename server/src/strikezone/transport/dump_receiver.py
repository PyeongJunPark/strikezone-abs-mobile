"""docs/protocol.md v2 형식의 TCP DUMP 수신 서버 모듈."""
from pathlib import Path
import socket
import struct
import tempfile
import time
from typing import Dict, Any, Optional, Tuple


class DumpReceiver:
    """모바일 앱에 DUMP 명령을 보내고 MP4 클립을 받는 TCP 서버."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9999):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.client_address: Optional[Tuple[str, int]] = None

    def start_server(self):
        """스마트폰 연결을 받을 주소에 바인딩하고 대기한다."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)

    def wait_for_client(self, timeout: Optional[float] = None) -> Tuple[str, int]:
        """모바일 앱이 접속할 때까지 대기한다."""
        if not self.server_socket:
            raise RuntimeError("Server socket is not started. Call start_server() first.")

        self.server_socket.settimeout(timeout)
        self.client_socket, self.client_address = self.server_socket.accept()
        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return self.client_address

    def send_dump_command(self, duration_seconds: float = 4.5):
        """스마트폰에 ASCII DUMP 명령을 전송한다."""
        if not self.client_socket:
            raise RuntimeError("No client connected.")

        command = f"DUMP {duration_seconds:.1f}\n".encode("ascii")
        self.client_socket.sendall(command)

    def receive_mp4_payload(self, output_path: Path, timeout: float = 5.0) -> Dict[str, Any]:
        """4바이트 Big-Endian 길이 헤더와 MP4 페이로드를 수신한다."""
        if not self.client_socket:
            raise RuntimeError("No client connected.")

        self.client_socket.settimeout(timeout)
        start_time = time.perf_counter()

        # 길이 헤더는 4바이트 Big-Endian 부호 없는 정수로 해석한다.
        header_bytes = self._read_exact(4)
        if len(header_bytes) != 4:
            raise ConnectionError("Client disconnected before sending a complete payload length header.")

        payload_length = struct.unpack("!I", header_bytes)[0]
        if payload_length <= 0:
            raise ValueError(f"Invalid payload length: {payload_length}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 같은 디렉터리의 임시 파일에 모두 받은 뒤 원자적으로 최종 경로에 반영한다.
        bytes_received = 0
        chunk_size = 64 * 1024
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f"{output_path.name}.", suffix=".part",
                dir=output_path.parent, delete=False,
            ) as f:
                temp_path = Path(f.name)
                while bytes_received < payload_length:
                    to_read = min(chunk_size, payload_length - bytes_received)
                    chunk = self.client_socket.recv(to_read)
                    if not chunk:
                        raise ConnectionError(
                            f"Connection lost while reading payload. Expected {payload_length} bytes, got {bytes_received}."
                        )
                    f.write(chunk)
                    bytes_received += len(chunk)
            temp_path.replace(output_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        elapsed_time = time.perf_counter() - start_time
        speed_mb_s = (bytes_received / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0.0

        return {
            "output_path": str(output_path),
            "payload_length": bytes_received,
            "elapsed_seconds": round(elapsed_time, 4),
            "transfer_speed_mb_s": round(speed_mb_s, 2),
        }

    def _read_exact(self, num_bytes: int) -> bytes:
        """클라이언트 소켓에서 num_bytes바이트를 채울 때까지 읽는다."""
        data = bytearray()
        while len(data) < num_bytes:
            packet = self.client_socket.recv(num_bytes - len(data))
            if not packet:
                break
            data.extend(packet)
        return bytes(data)

    def close_client(self):
        """서버 소켓은 유지하고 현재 클라이언트 연결만 닫는다."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
            self.client_socket = None
            self.client_address = None

    def close(self):
        """클라이언트와 서버 소켓을 모두 닫는다."""
        self.close_client()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None


def verify_mp4_integrity(file_path: Path) -> Dict[str, Any]:
    """비디오 파일을 열고 첫 프레임을 디코딩해 시작 프레임 손상을 확인한다."""
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

        # 첫 프레임을 디코딩해 시작 Key Frame의 복원 가능 여부를 확인한다.
        ok, frame = cap.read()
        cap.release()

        if ok and frame is not None and frame.size > 0:
            result["first_frame_decoded"] = True
            result["valid"] = True
        else:
            result["error"] = "Failed to decode the first frame"

    except ImportError:
        # cv2가 없으면 영상 디코딩 대신 MP4의 ftyp 상자 서명만 확인한다.
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
