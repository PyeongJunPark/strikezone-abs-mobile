"""Unit tests for the TCP dump receiver transport module."""
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
        """Test full DUMP trigger and MP4 streaming lifecycle over local loopback."""
        received_commands = []
        payload_data = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"TEST_PAYLOAD" * 1024

        def mock_client_thread():
            time.sleep(0.1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", self.port))
            reader = sock.makefile("r", encoding="ascii")

            # 1. Wait for DUMP command
            cmd = reader.readline().strip()
            received_commands.append(cmd)

            # 2. Send 4-byte Big-Endian length + payload
            sock.sendall(struct.pack("!I", len(payload_data)))
            sock.sendall(payload_data)
            sock.close()

        client_t = threading.Thread(target=mock_client_thread)
        client_t.daemon = True
        client_t.start()

        # Server: accept client
        self.receiver.wait_for_client(timeout=3.0)

        # Server: send DUMP command
        self.receiver.send_dump_command(duration_seconds=4.5)

        # Server: receive MP4 payload
        clip_path = self.test_dir / "received_clip.mp4"
        result = self.receiver.receive_mp4_payload(clip_path, timeout=3.0)

        client_t.join(timeout=2.0)

        # Verify command received by client
        self.assertEqual(len(received_commands), 1)
        self.assertEqual(received_commands[0], "DUMP 4.5")

        # Verify server received payload exactly
        self.assertEqual(result["payload_length"], len(payload_data))
        self.assertTrue(clip_path.is_file())
        self.assertEqual(clip_path.read_bytes(), payload_data)

        # Verify integrity parser
        verification = verify_mp4_integrity(clip_path)
        self.assertTrue(verification["valid"])

    def test_unexpected_disconnect_raises_connection_error(self):
        """Test that server handles premature client disconnection gracefully."""
        def disconnecting_client():
            time.sleep(0.1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", self.port))
            # Send length header claiming 1000 bytes, but send only 10 bytes then close
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


if __name__ == "__main__":
    unittest.main()
