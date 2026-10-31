# 수동 시작 기반 공 추적

구현 #24, 추적 제한점 #25, 통과 시점 #26, 존 비교 #27.

## 실행

저장소 루트에서 server/requirements.txt를 설치한 Python으로 실행한다.
영상과 YOLO 가중치는 별도로 준비하며 자동 다운로드하지 않는다.
실험은 BaseballCV ball 모델의 baseball 클래스 2를 사용했다. 다른 모델은 클래스 목록을 확인하고 ball_class를 바꾼다.

```powershell
python server/scripts/track_ball.py --video "input.mp4" --weights "ball.pt" --config "server/configs/ball-tracking.example.json" --output "outputs/my-pitch" --device cpu
```

CUDA는 --device 0을 사용한다. 출력 폴더는 새 경로여야 한다.
예시 설정은 1920×1080 실험 영상의 한 투구이므로 자신의 영상에 맞게 변경한다.

- trigger_frame: 원본 영상의 0부터 시작하는 수동 시작 프레임.
- pitcher_box: 공 출발 탐색 영역 [left, top, right, bottom], 원본 픽셀.
- plate_region: 홈플레이트 주변 목표 영역. 스트라이크존이나 통과 평면이 아니다.
- crop: 검출 입력 영역, 선택 사항. 결과는 원본 좌표로 복원한다.
- 카메라 이동 시 다시 설정하고, 투구마다 시작 프레임과 출력 폴더를 바꾼다.

시작 이후 최대 4초를 순차 디코딩한다. YOLO 입력 1280, confidence 0.08로 검출하고 원본 기준 한 변 100px 초과 후보는 제외한다.
연결은 confidence 0.12 이상 후보의 최근 선형 속도 예측과 거리 제한을 사용한다.
출발 영역의 움직임과 목표 접근 점수로 궤적 하나를 선택한다. 시작 후 2초 안에 획득하고 최대 1.5초의 궤적을 반환한다.
실제 투구 여부를 보장하는 분류기는 아니다. 투수·포수의 매 프레임 인식이나 포구 성공은 필수 조건이 아니다.

## 출력

detections.jsonl은 빈 프레임을 포함한 후보 목록, track.json은 offline-ball-track-v1 실험 형식이다.
기존 공통 분석 계약을 대체하지 않는다.

- track: 선택한 관측 궤적. 실패하면 빈 배열과 no_ball_track.
- positions: detected / interpolated / extrapolated / missing 구분.
- 보간은 양쪽 관측 간격 8프레임 이내, 외삽은 마지막 관측 뒤 최대 3프레임.
- uncertainty_px는 휴리스틱이며 통계적으로 검증한 신뢰구간이 아니다.
- endpoint는 기본 실행에서 보류한다. 포구·플레이트 통과·스트라이크 확정을 제공하지 않는다.
- 시간은 파일의 명목 FPS 기준으로 실제 촬영 시간이나 구속을 뜻하지 않는다.

모듈의 endpoint, compare_zone, analyze는 기존 실험 호환용이다. 화면상의 점 비교와 움직임 변화 후보이며 공식 판정이 아니다. CLI는 이 판정 경로를 사용하지 않는다.

## 검증과 제한점

실제 인터레이스 제거 경기 영상의 수동 시작 490프레임, 120프레임 구간을 CLI로 실행하여 관측점 18개의 궤적 출력을 확인했다.
이것은 실행·출력 확인이며 정확도 검증은 아니다. 인터레이스 제거는 별도 전처리이며 CLI가 자동 수행하지 않는다.
기존 48개 수동 구간 분석에서는 후보 45개, 실제 비행 일부 확인 37개, 오추적 7개, 도착부 조각 1개, 미검출 3개였다.
37개에도 공백·오연결이 있어 완전 추적 성공률로 해석하면 안 된다.
배트·신발·손·배경 오검출, 가려짐, 저해상도, 중복 프레임, 긴 공백은 #25에서 개선한다.
박스 크기는 실제 공 지름과 다르다. 영상·가중치·개인 실험 산출물은 커밋하지 않는다.

```powershell
python -m unittest discover -s server/tests -p "test_*.py"
node --test server/tests/test_fixed_zone.js server/tests/test_fixed_zone_page.js
```

회귀 테스트는 정지 후보 배제, 시작 범위, 포구 없이 반환, 보간·외삽 한계, crop 좌표 복원을 검증한다.
