"""TCP DUMP 수신 전송 모듈의 단위 테스트."""
from pathlib import Path
import shutil
import socket
import struct
import tempfile
import threading
import time
import unittest

from strikezone.transport.dump_receiver import DumpReceiver, verify_mp4_integrity


class TestDumpReceiverTransport(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.port = 19999  # 테스트용 비표준 포트
        self.receiver = DumpReceiver(host="127.0.0.1", port=self.port)
        self.receiver.start_server()

    def tearDown(self):
        self.receiver.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_loopback_dump_transfer(self):
        """로컬 루프백에서 DUMP 명령부터 MP4 수신까지 확인한다."""
        received_commands = []
        payload_data = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"TEST_PAYLOAD" * 1024

        def mock_client_thread():
            time.sleep(0.1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", self.port))
            reader = sock.makefile("r", encoding="ascii")

            # 서버가 DUMP 명령을 보낼 때까지 대기한다.
            cmd = reader.readline().strip()
            received_commands.append(cmd)

            # 4바이트 Big-Endian 길이 헤더 뒤에 페이로드를 전송한다.
            sock.sendall(struct.pack("!I", len(payload_data)))
            sock.sendall(payload_data)
            sock.close()

        client_t = threading.Thread(target=mock_client_thread)
        client_t.daemon = True
        client_t.start()

        # 서버에서 클라이언트 연결을 수락한다.
        self.receiver.wait_for_client(timeout=3.0)

        # 서버에서 DUMP 명령을 전송한다.
        self.receiver.send_dump_command(duration_seconds=4.5)

        # 서버에서 MP4 페이로드를 수신한다.
        clip_path = self.test_dir / "received_clip.mp4"
        result = self.receiver.receive_mp4_payload(clip_path, timeout=3.0)

        client_t.join(timeout=2.0)

        # 클라이언트가 받은 명령을 확인한다.
        self.assertEqual(len(received_commands), 1)
        self.assertEqual(received_commands[0], "DUMP 4.5")

        # 서버가 페이로드 전체를 받았는지 확인한다.
        self.assertEqual(result["payload_length"], len(payload_data))
        self.assertTrue(clip_path.is_file())
        self.assertEqual(clip_path.read_bytes(), payload_data)
        self.assertEqual(list(self.test_dir.glob("*.part")), [])

        # MP4 무결성 검사 결과를 확인한다.
        verification = verify_mp4_integrity(clip_path)
        self.assertTrue(verification["valid"])

    def test_unexpected_disconnect_raises_connection_error(self):
        """클라이언트가 전송 도중 끊겼을 때 서버 오류 처리를 확인한다."""
        def disconnecting_client():
            time.sleep(0.1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", self.port))
            # 1000바이트를 예고한 뒤 10바이트만 보내고 연결을 닫는다.
            sock.sendall(struct.pack("!I", 1000))
            sock.sendall(b"1234567890")
            sock.close()

        client_t = threading.Thread(target=disconnecting_client)
        client_t.daemon = True
        client_t.start()

        self.receiver.wait_for_client(timeout=3.0)
        clip_path = self.test_dir / "failed_clip.mp4"

        with self.assertRaises(ConnectionError):
            self.receiver.receive_mp4_payload(clip_path, timeout=3.0)

        client_t.join(timeout=2.0)
        self.assertFalse(clip_path.exists())
        self.assertEqual(list(self.test_dir.glob("*.part")), [])

    def test_failed_transfer_preserves_existing_clip(self):
        """교체 수신이 중단되어도 기존의 완성된 클립을 보존한다."""
        clip_path = self.test_dir / "existing_clip.mp4"
        clip_path.write_bytes(b"previous-complete-clip")

        def disconnecting_client():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("127.0.0.1", self.port))
                sock.sendall(struct.pack("!I", 1000) + b"partial")

        client_t = threading.Thread(target=disconnecting_client, daemon=True)
        client_t.start()
        self.receiver.wait_for_client(timeout=3.0)

        with self.assertRaises(ConnectionError):
            self.receiver.receive_mp4_payload(clip_path, timeout=3.0)

        client_t.join(timeout=2.0)
        self.assertEqual(clip_path.read_bytes(), b"previous-complete-clip")
        self.assertEqual(list(self.test_dir.glob("*.part")), [])

    def test_timeout_removes_partial_clip(self):
        """페이로드 수신이 멈춰도 불완전한 클립을 노출하거나 남기지 않는다."""
        def stalled_client():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("127.0.0.1", self.port))
                sock.sendall(struct.pack("!I", 1000) + b"partial")
                time.sleep(0.4)

        client_t = threading.Thread(target=stalled_client, daemon=True)
        client_t.start()
        self.receiver.wait_for_client(timeout=3.0)
        clip_path = self.test_dir / "timed_out_clip.mp4"

        with self.assertRaises(socket.timeout):
            self.receiver.receive_mp4_payload(clip_path, timeout=0.1)

        client_t.join(timeout=2.0)
        self.assertFalse(clip_path.exists())
        self.assertEqual(list(self.test_dir.glob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
