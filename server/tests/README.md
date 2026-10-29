# 서버 테스트
모듈 단위 검증과 모듈 간 통합 검증을 배치합니다. 테스트 도구와 실행 명령은 이슈 #3에서 확정합니다. 큰 영상·가중치를 테스트 코드에 포함하지 않으며 입력 자료는 data 안내를 참조합니다.

Pose·기준 추천: `.venv/Scripts/python.exe -m unittest discover -s server/tests -p "test_pose*.py"`

존 상태·화면 이벤트: `node --test server/tests/test_fixed_zone*.js` (Node 내장 테스트 실행기; 별도 npm 패키지 없음). 화면 이벤트 테스트는 DOM 대체 객체로 실행하며 브라우저 E2E 검증과 구분합니다.
