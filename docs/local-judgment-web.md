# 로컬 영상 업로드 · 타자 자세 · 투구 참고 판정

이슈 #27의 로컬 실행 기능이다. 영상 업로드 후 홈플레이트 좌우와 투구 시작 시점을 지정하면 타자 자세, 공 추적, 화면상 참고 판정과 표시 영상을 생성한다.

## 처음 준비하기 (Windows PowerShell)

명령은 클론한 저장소 루트에서 실행한다.

1. [uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)에 따라 uv를 설치하고 새 PowerShell을 연다. 아래 명령은 Python 3.12 가상환경과 의존성을 준비한다. NVIDIA GPU를 사용하려면 `cpu` 대신 `cu128`을 선택한다. 자세한 환경 조건은 [개발 환경](development.md)을 참고한다.

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1 -Backend cpu
   ```

2. 아래 두 공개 가중치를 내려받는다. 공 모델은 **BaseballCV ball_tracking_v4-YOLOv11**이며 클래스 `2`가 `baseball`인 모델을 사용해야 한다. 다른 YOLO 모델을 이름만 바꿔 넣으면 동일하게 동작하지 않는다.

   ```powershell
   New-Item -ItemType Directory -Force models | Out-Null
   Invoke-WebRequest 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-pose.pt' -OutFile models/pose.pt
   Invoke-WebRequest 'https://data.balldatalab.com/index.php/s/YkGBwbFtsf34ky3/download/ball_tracking_v4-YOLOv11.pt' -OutFile models/ball.pt
   ```

   공 모델 출처: [BaseballCV 다운로드 매니페스트](https://github.com/BaseballCV/BaseballCV/blob/main/models/od/YOLO/ball_tracking/model_weights/ball_trackingv4.txt). 링크가 변경되면 이 파일에서 새 주소를 확인한다. 모델 이용 조건은 각 배포처를 따른다.

3. [FFmpeg 공식 다운로드 페이지](https://ffmpeg.org/download.html)의 Windows builds 링크에서 실행 파일이 포함된 빌드를 내려받아 압축을 푼다. 압축 안의 `bin/ffmpeg.exe` 실제 경로를 아래 `--ffmpeg`에 넣는다. 예시 경로는 `C:/tools/ffmpeg/bin/ffmpeg.exe`다. 소스 코드 압축파일은 실행 파일이 아니다.

   ```powershell
   & 'C:/tools/ffmpeg/bin/ffmpeg.exe' -version
   .venv/Scripts/python.exe -c "from ultralytics import YOLO; p=YOLO('models/pose.pt'); b=YOLO('models/ball.pt'); assert p.task == 'pose'; assert b.names[2] == 'baseball', b.names; print('models OK')"
   ```

모델과 영상은 Git에 포함되지 않는다. 위 명령에서 오류가 나면 다운로드/설치와 경로를 확인한 후 실행한다.

## 실행

저장소 루트에서 개발 환경 Python 및 로컬 모델을 사용한다. 모델 다운로드·재학습은 서버가 자동 수행하지 않는다.

```powershell
.venv/Scripts/python.exe server/scripts/serve_judgment.py --pose-model models/pose.pt --ball-model models/ball.pt --ffmpeg C:/tools/ffmpeg/bin/ffmpeg.exe --device cpu --port 8785
```

CPU는 `--device cpu`, CUDA 환경을 준비한 NVIDIA GPU는 `--device 0`. 브라우저에서 `http://127.0.0.1:8785/`를 연다. 종료는 서버 터미널에서 Ctrl+C.
저장 위치 기본값은 `outputs/local-judgment`, `--output`으로 변경 가능하다. 서버는 127.0.0.1에만 바인딩하며 모델 작업은 한 번에 하나씩 실행한다.

## 사용 흐름

1. 최대 1GB의 영상을 업로드한다. 고정 카메라, 짧은 투구 클립을 권장한다. 자동 존 높이를 얻으려면 투구 시작 직전 약 2초의 타격 준비 자세도 남겨 자른다. 준비 자세가 없으면 수동·대체 높이를 지정한다.
2. 타자가 준비한 프레임에서 홈플레이트 좌우 끝 두 점을 클릭한다. 픽셀 좌표로 저장된다.
3. 프레임 슬라이더로 투구 시작을 선택한다. 이 순간 이전 최대 2초에서 자동 높이를 계산하고 이때 고정한다.
4. 타자 선택이 모호하면 선택 보조 사각형을 그린다. 높이를 직접 그리는 것이 아니라 해당 사람의 관절로 계산한다.
5. 타자가 없을 때만 수동 높이 모드를 켜고 위/아래를 지정한다. 미검출을 임의 높이로 대체하지 않는다.
6. 분석 버튼을 누른다. 시작 후 최대 4초를 공 검출하고 판정 영상·근거 JSON을 저장한다. 같은 영상에서 다른 시작 시점으로 재실행 가능하다.

## 높이와 투구 연결

- 기존 PoseDetector/BatterSelector를 사용한다. 플레이트 주변 사람 중 타격 자세 후보를 선택한다.
- 어깨와 골반의 중간을 존 상단, 양 무릎 평균을 하단으로 쓴다. 관절 신뢰도 최소 0.4, 약 0.2초 이상, 최소 3개 표본에서 관절 높이 범위가 몸통 길이의 25% 이내일 때 안정 자세로 확보한다. 해당 구간 중앙값을 사용한다.
- 타자 식별자가 바뀌면 이전 높이를 버린다. 유효 자세는 최대 3초 유지하고, 안정 구간이 없으면 같은 타자 관절의 중앙값을 사용한다. 그것도 없으면 명시적으로 저장한 대체 높이를 사용한다. 사용자가 준비 자세 기준 프레임을 선택하면 관절로 높이를 계산해 최대 5초 이전까지 명시적으로 사용한다.
- 안정 자세만 높이를 갱신한다. 기준 대비 관절 높이 변화가 몸통 길이의 30%를 넘으면 갱신을 보류하고, 연속 2표본에서 확인되면 직전 안정 존을 고정한다. 무릎의 골반 대비 높이와 신뢰할 수 있는 손목·발목도 참고한다. 투구 시작 후에도 고정한다. 스윙 자세가 판정 존을 바꾸지 않는다.
- 존을 못 만들면 `missing_stable_stance`, 공을 못 찾으면 `no_ball_observations`로 판단 불가다. 투수/포수의 매 프레임 검출은 요구하지 않는다.
- 공 검출에는 기존 ball.pt의 클래스2를 사용한다. 세로 영상은 빈 하늘을 줄인 입력으로 검출하고 좌표를 원본 픽셀로 복원한다.
- 판정은 `receiver_reference.py`를 연결한다. 경계 포함, 첫 도달 구간 제한과 조기 소실 보완 정책은 [참고 판정 문서](reference-judgment.md)를 따른다.

## 영상과 저장

노랑은 존, 보라는 관측한 타자 관절/상자, 초록은 공 궤적, 회색은 사건 이후 제외한 궤적이다.
준비 구간의 과거 관절을 투구 후 현재 관절처럼 그리지 않는다. 선택 위치 원은 해당 프레임 근처에서만 표시한다.
결과 디렉터리에 `config.json`, `result.json`, `detections.json`, `analysis.mp4`, `poster.jpg`, `validation.json`을 보존한다.
웹의 저장된 분석 목록에서 재시작 후에도 영상을 열 수 있다. 업로드 원본은 별도 ID 폴더에 유지된다.

## 검증 범위

- 새 경기09 및 직접 촬영 V06-R01/V07-R05/V08-R01/V09-R14는 공 모델을 새로 실행해 통합 검증했다.
- V07-R05/V09-R14는 실제 타자가 있으므로 자동 높이를 사용한다. 오래된 catalog의 absent 분류는 영상 확인 결과와 달라 사용하지 않았다.
- V06/V08은 타자 없어 수동 높이. 기타 6구간은 기존 공 궤적 재사용과 새 자세 추정 연결을 확인했다. V05 자동 선택 실패와 V10 공 관측 없음도 결과에 남겼다.
- 기존 단위 테스트와 세션 높이/고정/신선도/타자 변경 테스트를 실행했다. 웹에서 업로드→좌우 클릭→시작 선택→분석→결과 영상 생성까지 확인했다.
- 이 기능은 투구 시작 자동 탐지나 영상 전체의 자동 투구 분할을 포함하지 않는다. 카메라 이동 보정, 규정상 3D ABS 판정, 타격/헛스윙/바운드의 확정 구분도 제공하지 않는다.

안정 자세 상태는 영상에 searching_stance → stable_ready → motion_pending → locked로 표시한다. 시간·몸통 대비 임계값은 경험적 초기 설정이며 야구 규정값이 아니다. 천천히 지속되는 자세 변화나 긴 가림은 추가 검증이 필요하다.

### 조건 완화와 역할 구분

기본 파이프라인은 0.2초/3표본의 안정 자세를 우선한다. 안정 자세가 없으면 같은 타자에게서 최근 3초 이내 확보한 관절 2표본 이상의 중앙값을 사용하며, 큰 높이 이상치를 제외한다. 그래도 없으면 사용자가 그린 `fallback_height`를 사용한다. 명시적으로 선택한 준비 프레임 자체가 불량한 경우에는 다른 높이로 조용히 대체하지 않는다.

웹에서 수동·대체 높이 두 점을 그려두면 자동 높이 실패 시 대체한다. '타자 없음 / 수동 존 높이 사용'을 체크하면 기존처럼 수동 높이를 우선한다. 결과의 `height_source`는 `batter_pose`, `pose_median`, `manual_fallback`, `manual`을 구분한다.

자동 타자 선택은 플레이트 중앙의 포수/심판 후보, 전경의 큰 투수 후보, 다른 발 높이의 사람을 위치·크기로 제외한다. 투수 영역을 지정하면 해당 영역과 겹치는 후보도 제외한다. 타자 수동 영역은 이 자동 역할 제한을 우회하는 명시적 선택이다. 화면 각도나 보정 오차에 따른 오인식/과제외는 여전히 가능하며 `rejected_candidates`에 제외 이유를 남긴다.
