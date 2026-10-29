# 환경 검증 기록

## 2026-10-29 / 현재 개발 PC

| 항목 | 결과 |
| --- | --- |
| OS | Windows 11 |
| GPU | NVIDIA GeForce RTX 5080 16GB, 드라이버 610.88 |
| Python | 프로젝트 전용 3.12.13 |
| CUDA 환경 | torch 2.11.0+cu128 / torchvision 0.26.0+cu128 |
| CPU 전용 환경 | torch 2.11.0+cpu / torchvision 0.26.0+cpu |
| 기본 추론 | 두 환경 모두 영상 3프레임 읽기·YOLO11s Pose 추론 통과 |
| 순전파·역전파 | CPU 및 CUDA 합성 입력 검사 통과 |
| 의존성 | 두 환경에서 uv pip check 통과 |
| Python 설치 도우미 | cu128 환경에서 재실행 통과 |
| JDK | Microsoft OpenJDK 17.0.21 |
| Android SDK | Platform 35 / Build-Tools 35.0.0 / Platform-Tools 설치 |
| APK | Gradle Wrapper 및 build-android.ps1의 assembleDebug 성공 |
| Gradle 공급 파일 | wrapper JAR 및 배포 ZIP SHA-256 검증 |
| Android Studio IDE | 이 PC에서는 미설치, 명령행 빌드로 검증 |
| 실기기 | adb devices에 연결 기기 없음, 설치·화면 미검증 |
| 다른 팀원 PC | 미검증 |

입력은 기존 화면 녹화 `20261029-0516-23.5662831.mp4`(906×770, 파일상 30fps)와 로컬 `yolo11s-pose.pt`입니다. 모델 SHA-256: `1060bda4a27012060eca246f9b2adeea22eabb045a1e58f8d229be29b7ebc2ba`.

각 프레임에서 사람 검출 5개와 17개 관절 좌표가 반환되었습니다. 타자 선택·공 검출·판정 정확도를 확인한 결과는 아닙니다. GPU 초기화 이후 두 프레임은 약 8~9ms, CPU 전용 환경은 약 39~42ms였으며 표본이 매우 작고 준비 비용·영상 전송·공 분석을 제외하므로 실시간 성능 수치로 사용하지 않습니다. 실제 모델 학습 작업은 수행하지 않았습니다.

## 알려진 사항

- 최신 SDK 도구와 AGP 8.9.2 조합에서 SDK XML 버전 경고가 발생했으나 APK 빌드는 성공했습니다.
- 개인 환경은 `.venv/`, CPU 별도 검증 환경은 `.venv-cpu/`에 있으며 Git에서 제외됩니다.
- 설치한 JDK는 사용자 폴더 `.local/share/strikezone-tools/jdk17/`, SDK는 사용자 LocalAppData의 `Android/Sdk/`에 있습니다. 전역 Java 설정은 변경하지 않았습니다.
- 실기기 고속 촬영, 앱 통신, 실제 학습, 다른 팀원 환경은 후속 확인 대상입니다.

## 팀원 확인 양식

| 담당자 | OS / GPU | Python 추론 | Android 빌드 | 기종 / Android 버전 | 앱 실행 / 촬영 모드 | 확인일 |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
