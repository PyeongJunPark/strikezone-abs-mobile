# 영상 분석 서버
Python 기반 영상 분석·판정 코드를 관리합니다. 판정 서버 기능은 아직 구현되지 않았으며 환경 검증용 스크립트를 제공합니다.

- `src/strikezone/pose/`: 타자 선택, 관절 추정, 존 높이 계산
- `src/strikezone/plate/`: 홈플레이트 검출, 보정, 존 좌우 기준
- `src/strikezone/ball/`: 공 검출과 프레임 간 추적
- `src/strikezone/judgment/`: 존 고정과 판정 상태, 통과 시점·볼/스트라이크/판정 불가 처리
- `src/strikezone/transport/`: 앱 연결, 영상 수신, 결과 송신
- `src/strikezone/common/`: 모듈 간 공유하는 데이터 형식과 유틸리티
- `tests/`: 단위·통합 검증

서버 기능은 experiments의 임시 코드를 직접 의존하지 않습니다. 검증된 로직을 해당 모듈로 옮겨 사용합니다. 공통 코드는 실제 여러 모듈이 공유할 때 추가하며, 모듈 전용 함수는 각 모듈에 둡니다.

설치·실행은 [개발 환경 안내](../docs/development.md)를 따릅니다. `requirements.txt`에 직접 의존성을 고정했으며 `scripts/check_environment.py`로 영상 읽기와 CPU/GPU 기본 추론을 확인합니다.
