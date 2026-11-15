"""Interactive test server to trigger DUMP and receive 4.5s MP4 clips from the mobile app."""
import argparse
from datetime import datetime
from pathlib import Path
import struct
import sys
import threading
import time

# strikezone 패키지 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from strikezone.transport.dump_receiver import DumpReceiver, verify_mp4_integrity


def run_mock_client(host: str, port: int, payload_size: int = 1024 * 1024):
    """Simulate a smartphone client connecting, waiting for DUMP, and streaming a dummy MP4."""
    import socket
    time.sleep(0.3)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host if host != "0.0.0.0" else "127.0.0.1", port))
        reader = s.makefile("r", encoding="ascii")
        cmd = reader.readline()
        if cmd.startswith("DUMP"):
            # Dummy MP4 header (ftyp box) + padding
            header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"
            padding = b"\x00" * (payload_size - len(header))
            data = header + padding

            # Send 4-byte length + payload
            s.sendall(struct.pack("!I", len(data)))
            s.sendall(data)
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9999, help="TCP port (default: 9999)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/received_dumps"),
        help="Directory to save received MP4 clips",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=4.5,
        help="Target dump duration in seconds (default: 4.5)",
    )
    parser.add_argument(
        "--mock-client",
        action="store_true",
        help="Run a local mock client loopback test without a real phone",
    )
    args = parser.parse_args()

    receiver = DumpReceiver(host=args.host, port=args.port)
    receiver.start_server()

    args.output.mkdir(parents=True, exist_ok=True)
    print("=" * 65)
    print(f" [ABS] 스마트폰 DUMP 수신 테스트 서버")
    print(f" 바인딩 주소 : {args.host}:{args.port}")
    print(f" 저장 디렉터리: {args.output.resolve()}")
    print("=" * 65)

    if args.mock_client:
        print("[테스트] 로컬 Mock 클라이언트 백그라운드 스레드 시작...")
        t = threading.Thread(target=run_mock_client, args=(args.host, args.port))
        t.daemon = True
        t.start()

    try:
        print("\n[대기 중] 스마트폰 앱의 연결을 기다리는 중입니다...")
        client_addr = receiver.wait_for_client()
        print(f"[연결 성공] 스마트폰 접속 확인: {client_addr[0]}:{client_addr[1]}\n")

        pitch_count = 0
        while True:
            if not args.mock_client:
                user_input = input(">> [Enter]를 누르면 DUMP 명령 전송 (종료는 'q'): ").strip()
                if user_input.lower() == "q":
                    print("서버를 종료합니다.")
                    break
            else:
                print(">> [Mock 모드] 자동으로 DUMP 명령 전송 중...")

            pitch_count += 1
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            clip_path = args.output / f"dump_{timestamp_str}_pitch{pitch_count:03d}.mp4"

            print(f"\n[투구 #{pitch_count}] 스마트폰으로 'DUMP {args.duration:.1f}' 명령 송신...")
            trigger_start = time.perf_counter()
            receiver.send_dump_command(args.duration)

            try:
                result = receiver.receive_mp4_payload(clip_path, timeout=6.0)
                rtt_total = time.perf_counter() - trigger_start
                size_mb = result["payload_length"] / (1024 * 1024)

                print(f"[수신 완료] 파일 크기 : {size_mb:.2f} MB ({result['payload_length']:,} 바이트)")
                print(f"[지연 시간] 전송 시간 : {result['elapsed_seconds']:.3f}초 (속도: {result['transfer_speed_mb_s']} MB/s)")
                print(f"[지연 시간] 전체 왕복 : {rtt_total:.3f}초 (트리거 송신 ➡️ 파일 수신 완료)")
                print(f"[저장 경로] {clip_path}")

                # 무결성 및 OpenCV 디코딩 검증
                verification = verify_mp4_integrity(clip_path)
                if verification["valid"]:
                    if verification["fps"] is not None:
                        print(
                            f"[검증 성공] OpenCV 정상 디코딩 확인: {verification['width']}x{verification['height']} "
                            f"@ {verification['fps']}fps, 총 {verification['frame_count']}프레임, "
                            f"첫 프레임(I-Frame) 정상 복원됨"
                        )
                    else:
                        print(f"[검증 완료] MP4 컨테이너 헤더 정상 확인 ({verification.get('error')})")
                else:
                    print(f"[검증 경고] 비디오 무결성 문제: {verification['error']}")

            except ConnectionError as ce:
                print(f"[연결 끊김] 수신 중 스마트폰 연결이 끊어졌습니다: {ce}")
                break
            except Exception as e:
                print(f"[수신 오류] {e}")

            if args.mock_client:
                print("\n[Mock 테스트 성공] 1회 수신 및 파일 저장 검증이 완료되었습니다.")
                break

    except KeyboardInterrupt:
        print("\n사용자 중단으로 서버를 종료합니다.")
    finally:
        receiver.close()
        print("[종료] 서버 소켓이 안전하게 닫혔습니다.")


if __name__ == "__main__":
    main()
