# 단일 카메라 오프라인 참고 판정

기존 공 추적 결과와 수동 존을 입력받아 화면상 참고 위치를 선택한다.
실제 홈플레이트 깊이 통과나 포구를 확정하지 않으며 앱·서버의 공식 판정 계약을 변경하지 않는다.
관련 이슈: #26. 이번 작업은 참고 판정 프로토타입으로 마무리하며, 실제 통과 시점 오차 검증 완료를 뜻하지 않는다.

## 실행

저장소 루트에서 개발 환경의 Python을 사용한다. 의존성은 `server/requirements.txt`를 따른다.

```powershell
python server/scripts/judge_reference.py --input data/examples/reference-pitch.json --output outputs/reference-result.json
$env:PYTHONPATH = 'server/src'
python -m unittest discover -s server/tests
```

예제는 합성 데이터이며 `STRIKE_ESTIMATE`, `disappearance_near_receiver`가 나온다.
이 CLI는 영상에서 공을 새로 검출하지 않는다. 기존 `ball/manual_pitch.py`의 `track`과 수동 보정을 입력으로 넘긴다.

## 입출력

- `track`: `frame_index`, `center_xy`(원본 픽셀), 선택적 `bbox_xyxy`, `observed`, `source_frame_repeated`.
- `zone`: `[left, top, right, bottom]`, `fps`: 실제 영상 FPS. 프레임은 검출 순서가 아니라 원본 시간축 번호다.
- `receiver`: 선택적 검색 영역. 생략하면 존으로부터 확장한다. 실제 포수 검출 상자가 아니다.
- `detections`: 프레임별 전체 후보 목록. 소실 확인에는 빈 후보 프레임도 필요하다. `end_frame`은 분석 끝 경계다.
- `size_rows`: 선택적 `frame`, `perpendicular_px`, `repeated`. 같은 프레임 기준 크기 관측이며 예상치를 재입력하지 않는다.
- `image_size`: `[width, height]`. 화면 밖 예측 판단에 사용한다.

출력 `preview`는 `STRIKE_ESTIMATE`, `BALL_ESTIMATE`, `UNJUDGEABLE`이다.
기존 경계 허용치 `max(3px, 존 폭의 8%)`는 스트라이크에 포함하며 `boundary_hit`로 구분한다.
이는 실제 공 반지름을 이용한 규정상 접촉 판정이 아니다.
`position.source`는 관측·보간·짧은 외삽·예측을 구분한다. `confidence`는 확률이 아니다.
`validated`, `confirmed_catch`, `confirmed_plate_crossing`은 모두 false다.

## 처리 방식

1. 앞뒤 이동이 일관된 단발성 이상점만 필터링한다. 입력은 변경하지 않으며 제외 이유를 반환한다.
2. 첫 포수 주변 영역 접근 후 연속 이탈하면 판정 구간을 제한한다. 이후 공 추적 자체를 삭제하는 것은 아니다.
3. 포수 근처 검출 공백 전후 방향 변화, 비행 뒤 고정점으로 잘못 연결되는 경우를 분리한다. 공백 안의 접촉 시점은 확정하지 않는다.
4. 지속적인 방향 변화·감속·소실 후보 직전 위치를 우선 사용한다. 접촉 종류(포구/타격/바운드)는 자동 구분하지 못한다.
5. 이벤트가 없으면 포수 근처 관측을 사용한다. 조기 소실은 크기·궤적 예측으로 보완하고 계산 불가 시 최근접 관측으로 대체한다.

`ball/masking.py`는 시간 배경과의 차이로 마스크를 만들고, `blur_size.py`는 이동 방향에 수직인 두께를 계산한다.
`size_forecast.py`는 시간에 대해 역지름을 선형, 위치×역지름을 이차식으로 근사한다. 중력을 보정한 3D 물리 모델이 아니다.

## 검증과 남은 문제

- 로컬 92구간 재계산. 첫 도달 구간 수정은 직전 버전 대비 선택 위치 8개 변경, 스트라이크/볼 변경 0개.
- V06-R01: f493→470, V09-R03: f2118→2094, V09-R04: f2670→2652. 늦은 바운드 대신 앞선 관측을 사용한다.
- V13-R03: 고정점 f2302 대신 마지막 비행 관측 f2296. 실제 접촉 시점은 f2296~2300 사이로 불확실하다.
- 이상점 필터: 기존 추적 관측 1,259개에서 자동 제외 0개. 검토 후보 6개는 실제 변화 가능성이 있어 자동 삭제하지 않았다.
- 새 경기 GAME_VID_000009의 32~42초: 15프레임 연속 추적, 임시 존 기준 f187에서 스트라이크 추정. 타자 스윙 포함. 모델 학습 데이터 중복은 미확인.
- 보고서 대표 사례: V07-R05, V09-R14. 표본 결과는 정확도 평가가 아니다.
- 크기/마스크 오차가 도착 시간을 왜곡할 수 있다. 현재 실험 정책은 불안정한 예측도 낮은 신뢰도로 노출하고 화면 밖 예측을 볼로 처리한다. 마지막 관측보다 앞선 도착 예측을 완전히 배제하지 않는다.
- 최근접 관측 대체는 실제 도착을 보증하지 않는다. 수동 존, 가림, 카메라 이동, 잘못된 연결에 민감하다.

실패한 시도와 변경 이력은 [실험 기록](one-camera-experiments-and-limitations.md)에 보존한다.
실제 영상·가중치·사용자 보정 파일·개인 경로 기반 실험 스크립트는 게시하지 않는다.
