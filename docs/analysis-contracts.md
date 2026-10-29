# 녹화 영상 분석 계약 v1

상태: 구현을 위한 제안 초안. 이 문서는 공식 ABS 규정이나 검증된 판정 알고리즘이 아닙니다. 폰 1대의 녹화 영상 분석을 대상으로 하며 TCP wire format은 [별도 문서](protocol.md)에서 추후 정의합니다.

## 공통 입력과 결과

프레임 입력은 기준 영상의 BGR uint8 H×W×3 배열과 video_id, pitch_id, frame_index, pts_ms, time_source, image_width, image_height를 갖습니다. 배열은 프로세스 내부 입력이며 JSON 예시에서는 생략합니다. 모든 반환 좌표는 [기준 좌표](coordinates.md)로 복원합니다.

결과는 `schema_version=analysis-v1`, 입력 식별자와 모듈별 결과를 포함합니다. 각 모듈은 `status`, `confidence`, `reason`을 반환합니다.

- status: `ok`, `missing`, `invalid`, `not_run`.
- confidence: 모델 신뢰도 0~1 또는 null. 수동 입력은 null이며 1.0으로 위조하지 않습니다. 서로 다른 모델 점수를 곱해 판정 확률처럼 사용하지 않습니다.
- reason: 일반 모듈은 ok면 null, 나머지는 `low_confidence`, `occluded`, `no_detection`, `invalid_geometry`, `not_configured` 등의 코드.
- 없는 값은 null/빈 목록이며 NaN, Infinity, (0,0) 대체값을 사용하지 않습니다.

## 모듈 책임

| 모듈 | 입력 | 출력 |
| --- | --- | --- |
| pose | 프레임, 타자 선택 ROI/track ID, 관절 신뢰도 설정 | 타자 ID, bbox, 이름별 keypoints(x,y,confidence), 존 높이 후보 |
| plate | 프레임, 수동 기준점 또는 검출 설정 | 홈플레이트 꼭짓점, 판정용 앞변 좌우 기준, manual/auto 출처 |
| ball | 프레임, 검출·추적 설정, 이전 track 상태 | 후보 bbox/중심, track ID, observed/interpolated, 신뢰도 |
| judgment | 고정 존, 공 track, 통과 시점 근거, 스윙 상태, 투구 상태 | preview 결과, 최종 판정 또는 판정 불가 사유 |
| common | 공유 식별자·좌표 변환·상태 정의 | 공통 자료형 및 검증 함수; 전용 모델 로직은 넣지 않음 |
| transport | 향후 앱 메시지 | 프로토콜 확정 전에는 내부 계약을 wire format으로 가정하지 않음 |

분석 파이프라인은 각 모듈을 호출해 묶습니다. pose와 plate는 ball에 의존하지 않습니다. 파일 읽기/화면 출력 코드를 모델 모듈 안에 섞지 않습니다.

## 초기 존 계산: pose-midpoint-v1

공식 규칙의 신체 경계를 직접 측정한 것이 아닌 **관절 기반 근사식**입니다. 타자 선택과 기준 프레임은 초기에는 사람이 지정합니다.

양쪽 shoulder·hip·knee 총 6개 관절이 설정 임계치 이상일 때만 사용합니다. 임계치는 설정값이며 예시 실험 시작값은 0.5, 검증 결과에 따라 바꿉니다. 한쪽 누락 시 반대쪽을 자동 복제하지 않습니다.

`shoulder_y=(left_shoulder_y+right_shoulder_y)/2`
`hip_y=(left_hip_y+right_hip_y)/2`
`knee_y=(left_knee_y+right_knee_y)/2`
`top_y=(shoulder_y+hip_y)/2`, `bottom_y=knee_y`

shoulder_y < hip_y < knee_y와 top_y < bottom_y를 요구합니다. 무릎 관절 중심은 무릎의 규칙상 경계와 같지 않으므로 정답 존과 비교해 평가해야 합니다.

초기 화면 미리보기의 좌우 경계는 **홈플레이트에서 투수 쪽을 향하는 폭 방향 앞변의 양 끝점**을 영상 x 순서로 정렬해 min/max x로 설정합니다. plate 꼭짓점은 화면 투영의 앞변 왼쪽, 앞변 오른쪽, 뒤쪽 오른쪽, 뒤 꼭짓점, 뒤쪽 왼쪽 순서로 기록합니다. 가림·해당 변 식별 실패 시 수동 지정하거나 missing을 반환합니다.

앞변 x를 위로 연장한 사각형은 시점 왜곡을 무시한 `image_rect_approx_v1` 미리보기입니다. 43.18cm를 화면 전체의 공통 cm/pixel 비율로 적용하지 않습니다. 이 근사 사각형만으로 실제 통과 여부를 확정하지 않습니다.

## 존 고정 및 투구 상태

`idle → ready → tracking → completed`를 사용합니다. 각 상태에서 취소하면 cancelled가 되며, 새 투구 ID로 명시적으로 초기화합니다.

- ready: 타자와 홈플레이트가 유효한 상태에서 수동 lock. zone_id, reference_frame_index, 계산식·설정 버전과 좌표 저장.
- tracking: 수동 투구 시작. 고정 존을 유지하고 공 관측을 수집.
- completed: 투구 종료 후 결과 1개만 발행. 재실행 결과는 revision을 올리고 이전 결과와 구분.
- 타자 변경·카메라 움직임·보정 변경 시 고정 존 무효화. 초기에는 사용자가 reset하며 자동 움직임 감지는 구현 완료로 간주하지 않음.
- 유효한 존 없이 시작하면 tracking으로 넘어가지 않고 invalid_zone을 반환.

## 공과 통과 시점

공 중심·bbox와 관측 시각을 저장합니다. 검출은 observed, 보간은 interpolated로 구분합니다. bbox 절반을 정확한 공 반지름으로 간주하지 않습니다. radius_px는 별도 추정 방법과 오차 검증 없이는 null입니다.

crossing은 `status`, `method`, `frame_index`, `pts_ms`, `center_xy`, `radius_px`, `reason`, `validated`를 갖습니다. 초기 method는 `manual_frame`, `size_ratio_experimental`, `none`이며 모두 기본 validated=false입니다. 수동 프레임 선택은 화면 미리보기 검사용이며 공간 정답을 보증하지 않습니다.

공 크기 비율·궤적으로 홈플레이트 앞면 도달을 찾는 방법은 미검증입니다. 홈플레이트 판정 위치의 공간 보정과 오차가 검증되기 전에는 crossing.validated를 true로 설정하지 않습니다.

## 결과와 경계 처리

스윙 상태는 `swing`, `no_swing`, `unknown`입니다. 초기 수동 입력도 source=manual로 허용합니다.

1. swing → excluded_swing (위치 판정 범위 밖).
2. unknown → unjudgeable / swing_unknown.
3. 고정 존·track·통과 근거가 누락/무효 → unjudgeable와 해당 사유.
4. 공간 보정 또는 crossing이 미검증 → unjudgeable / unvalidated_geometry.
5. 검증된 방식이 마련된 후에만 최종 strike/ball을 활성화합니다. 현재 구현 범위에서는 최종 자동 판정이 아닙니다. judgment.status는 판정 함수의 정상 수행 여부이므로 value=unjudgeable이어도 ok일 수 있으며, 이 경우 reason에 판정 불가 사유를 기록합니다.

대신 `preview` 필드로 **2D 미리보기**를 제공합니다. 반지름이 알려진 원과 축 정렬 존 사각형의 최근접점 q를 구하고 d=공 중심과 q의 거리로 둡니다. `d <= r`이면 touches_zone, 그 외 outside_zone입니다. r 또는 crossing 중심이 없으면 unknown입니다. 경계 접촉도 겹침으로 포함하되 실제 최종 판정과 구분합니다.

향후 오차 반경 epsilon이 검증되면 d-r의 절대값이 epsilon 이내인 경우 uncertain_boundary로 처리할 수 있습니다. epsilon=0을 임의로 정확한 측정이라고 간주하지 않습니다. 최종 실제 공간의 판정 부피·경계 기준은 별도 실험·합의가 필요합니다.

## 예시

[정상 관측 예시](examples/analysis-observed.json)는 pose·plate·ball이 유효하지만 공간 통과가 미검증이므로 최종 결과는 unjudgeable입니다. [누락 예시](examples/analysis-missing.json)는 관절·공 누락을 표현합니다. 두 파일은 합성 자료이며 정답·실제 성능 결과가 아닙니다.
