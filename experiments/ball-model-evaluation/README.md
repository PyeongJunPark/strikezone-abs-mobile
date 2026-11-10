# 공 검출 모델 평가

검토된 `labels-v1` 프레임 라벨과 `track_ball.py`가 생성한 `detections.jsonl` 후보를 비교한다.
영상이나 모델 가중치 없이도 합성 JSONL로 평가 계산과 회귀 테스트를 실행할 수 있다.

## 실행

```powershell
.venv/Scripts/python.exe server/scripts/evaluate_ball_detections.py `
  --labels data/labels/dataset-v001/video.jsonl `
  --detections outputs/run-001/detections.jsonl `
  --video-id 20261029_s01_c01_v001 `
  --output outputs/run-001/evaluation.json
```

기본 매칭 기준은 박스 IoU 0.5 이상 또는 중심 거리 8px 이하다. `--iou-threshold`와
`--center-threshold-px`로 바꿀 수 있다. 검출 파일에 `video_id`가 없으면 단일 영상의
ID를 `--video-id`로 지정한다.

기본값은 `reviewed`, `approved`, `verified`, `final` 라벨만 평가한다. `draft`를 임시로
포함하려면 `--include-draft`를 사용하되 최종 성능으로 보고하지 않는다. `uncertain`과
좌표가 없는 라벨은 음성 표본이 아니므로 건너뛴다. 검토된 `out_of_frame`만 명시적인
음성 프레임으로 사용한다.

보고서는 TP, FP, FN, Precision, Recall, F1, 매칭된 중심 오차 평균·중앙값·95백분위,
평균 IoU와 프레임별 근거를 저장한다. 한 프레임에 후보가 여러 개면 하나만 TP가 될 수
있고 나머지는 FP다.

## 테스트

```powershell
.venv/Scripts/python.exe -m unittest server.tests.test_ball_evaluation
```

실제 데이터 평가 전에는 라벨의 독립 검토 여부, 데이터 버전, 모델 가중치 해시와 코드
커밋을 함께 기록한다. 같은 촬영 세션의 인접 프레임이 학습과 평가에 나뉘지 않도록 한다.
