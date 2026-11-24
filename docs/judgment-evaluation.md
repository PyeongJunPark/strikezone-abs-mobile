# 볼·스트라이크 판정 정확도 평가 (제안)

상태: 평가 도구 구현 완료, 정답 기준은 **팀 합의 필요**. 제안서 목표는 100구 이상에서 정확도 80% 이상입니다.

## 정답 기준 제안

제안서는 "홈플레이트 앞면 타겟 프레임 기준 정답과 비교"였지만, 현재 판정은 포수 근처 도착 위치를 쓰는 참고 판정이고 30fps에서는 앞면 통과 프레임을 사람이 정확히 고를 수도 없습니다. 그래서 아래 기준을 제안합니다.

1. **정답은 사람이 영상을 보고 내린 볼/스트라이크**로 합니다. 현장 심판 콜이 있으면 함께 기록합니다(`umpire_call`).
2. 라벨러 2명이 서로의 답을 보지 않고 따로 표시합니다. 일치하면 그 값을, 불일치하면 `UNKNOWN`으로 두고 평가에서 제외합니다(제외 개수는 보고서에 남김).
3. 타자가 스윙한 투구는 `SWING`으로 표시하고 평가에서 제외합니다(제안서 범위: 스윙하지 않은 투구만 판정).
4. 파이프라인이 `UNJUDGEABLE`을 내거나 결과가 없으면 **오답으로 계산한 엄격 정확도**를 주 지표로 씁니다. 판정한 투구만의 정확도와 판정률(coverage)을 함께 보고합니다.
5. 라벨러는 판정 결과를 보기 전에 라벨을 작성합니다.

## 파일 형식

정답 라벨 (`labels.jsonl`, 한 줄에 투구 하나):

```json
{"pitch_id": "20261201_s01_p001", "truth": "STRIKE", "labeler_a": "STRIKE", "labeler_b": "STRIKE", "umpire_call": null, "note": ""}
```

`truth`: `STRIKE`, `BALL`, `SWING`, `UNKNOWN`.

판정 결과 (`predictions.jsonl`): `preview`를 직접 쓰거나 파이프라인 결과 파일 경로를 적습니다.

```json
{"pitch_id": "20261201_s01_p001", "result_json": "runs/abc123/result.json"}
{"pitch_id": "20261201_s01_p002", "preview": "BALL_ESTIMATE"}
```

예시: `data/examples/judgment-labels.example.jsonl`, `data/examples/judgment-predictions.example.jsonl`

## 실행

```powershell
python server/scripts/evaluate_judgments.py --labels labels.jsonl --predictions predictions.jsonl --output outputs/evaluation
```

`report.md`(발표용 요약)와 `report.json`을 저장합니다. 포함 내용:

- 엄격 정확도·판정 투구 정확도·판정률, 각각 95% Wilson 신뢰구간
- 스트라이크/볼 재현율, 혼동 행렬(정답 × STRIKE/BALL/UNJUDGEABLE/MISSING)
- 판정 근거(`decision_source`)·신뢰도·경계 근처(`boundary_hit`)별 정확도
- 오답·판정 불가·누락 목록과 목표(80%, 100구) 달성 여부

## 일정 (12/01~12/07)

1. 촬영: 고정 카메라, 30fps, 세션별 메타데이터 기록 ([촬영 가이드](capture-guide.md))
2. 라벨링: 2인 독립 라벨 → `labels.jsonl`
3. 판정 실행: 판정 웹에서 투구별 분석 → `predictions.jsonl`에 결과 경로 기록
4. `evaluate_judgments.py` 실행 → 오답 목록으로 원인 분석
