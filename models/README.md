# 모델

팀 공유 위치는 **미정**입니다. 로컬 GPU에서 학습하며 가중치는 Git에 포함하지 않습니다.

- `weights/<model_id>/`: 사전학습·자체학습 가중치
- `records/`: 실제 모델별 출처·학습·평가 기록
- `examples/model-record.example.json`: 기록 양식

[데이터 관리 규칙](../docs/data-management.md)에 따라 버전과 SHA-256을 확인한 뒤 배치합니다. 개인 환경 설정에서 실제 가중치 경로를 지정합니다. 공개 사전학습 모델을 이용한 환경 검사는 [개발 환경 안내](../docs/development.md)를 참고합니다. 팀에서 학습한 모델의 다운로드 위치는 아직 정해지지 않았습니다.
