# 개발 환경

폰 1대 + 로컬 분석 서버를 기준으로 합니다. 모델 학습은 로컬 GPU에서 진행하며 Colab은 필수가 아닙니다. 아래 버전은 프로젝트 기준이며 최신 버전을 의미하지 않습니다.

## Python / Windows

| 구성 | 기준 |
| --- | --- |
| Python | 3.12.13 |
| PyTorch / torchvision | 2.11.0 / 0.26.0 |
| NVIDIA 런타임 | PyTorch cu128 wheel |
| CPU 환경 | 같은 버전의 CPU wheel |
| Ultralytics | 8.4.107 |
| OpenCV | 4.13.0.92 |
| NumPy | 2.2.6 |

[uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)에 따라 uv를 설치합니다. 저장소 루트에서 PowerShell로 실행합니다.

```powershell
# NVIDIA GPU 사용 PC
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1 -Backend cu128
# GPU 없는 PC에서는 위 명령 대신 아래 명령
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1 -Backend cpu
```

직접 의존성은 `server/requirements.txt`, Windows/Python 3.12의 검증된 전이 의존성은 `server/constraints-windows-py312.txt`로 고정합니다. CPU 전용 wheel도 별도 가상환경에서 기본 추론을 확인했습니다. 다른 팀원 PC에서는 재확인이 필요합니다.

기존 전역 Python 패키지는 수정하지 않습니다. 기본 실행은 `.venv/Scripts/python.exe`를 직접 사용하며 활성화가 필요하면 `.venv/Scripts/Activate.ps1`을 실행합니다. 전역 실행 정책은 바꾸지 않습니다.

GPU 환경은 호환되는 NVIDIA 드라이버가 필요합니다. `nvidia-smi`의 CUDA 표시는 드라이버 지원 수준이고 `torch.version.cuda`는 설치된 PyTorch 런타임입니다. 일반 wheel 실행을 위해 시스템 CUDA Toolkit을 별도로 설치할 필요는 없지만 사용자 정의 CUDA 확장을 빌드하는 경우는 별도입니다. 다른 제조사 GPU는 이 구성의 검증 대상이 아니며 CPU로 먼저 확인합니다.

## 영상 읽기와 기본 추론

1. 팀에서 정한 공통 원본 영상을 로컬에 받습니다. 영상 공유·버전 확정은 이슈 #4에서 진행합니다.
2. 신뢰할 수 있는 출처의 YOLO11 Pose 가중치를 `models/`에 배치합니다. 공식 예: [yolo11s-pose.pt](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-pose.pt).
3. `configs/environment.example.json`을 `configs/environment.local.json`으로 복사합니다.
4. `video`, `model` 경로와 `device`를 수정합니다. 상대 경로는 저장소 루트 기준, GPU는 `"0"`, CPU는 `"cpu"`입니다. 개인 경로가 든 local 파일은 Git에서 제외됩니다.

```powershell
.venv/Scripts/python.exe server/scripts/check_environment.py --config configs/environment.local.json
```

검사는 영상 프레임 읽기, 기본 Pose 추론, 작은 합성 입력의 순전파·역전파를 실행합니다. JSON 결과에 버전, 모델 해시, 프레임별 시간·검출 수를 저장합니다. 첫 프레임은 초기화 비용을 포함합니다. 판정 정확도·실시간 성능·실제 학습 완료를 입증하는 검사는 아닙니다.

## Android

| 구성 | 기준 |
| --- | --- |
| Android Studio | Meerkat 2024.3.1 계열 또는 AGP 8.9 지원 버전 |
| Gradle JDK | 17 |
| Android Gradle Plugin | 8.9.2 |
| Gradle Wrapper | 8.11.1 |
| Kotlin | 2.1.20 |
| compileSdk / targetSdk | 35 |
| minSdk | 26 (Android 8.0) |

[AGP 호환성 문서](https://developer.android.com/build/releases/agp-8-9-0-release-notes)를 기준으로 선정했습니다. IDE 자동 업그레이드는 팀 합의 후 진행합니다.

Android Studio에서 `android/`를 열고 Gradle JDK를 17로 지정합니다. SDK Manager에서 Android SDK Platform 35, Build-Tools 35.0.0, Platform-Tools를 설치합니다. SDK 약관은 설치 과정에서 확인합니다. SDK 경로는 Git에서 제외되는 `android/local.properties`에 `sdk.dir=C:/.../Android/Sdk` 형식으로 설정하거나 `ANDROID_HOME`으로 지정합니다. Java 8로는 빌드할 수 없습니다.

```powershell
# 해당 터미널에서만 실제 설치 위치로 지정
$env:JAVA_HOME = 'C:/path/to/jdk-17'
cd android
.\gradlew.bat --version
.\gradlew.bat assembleDebug
```

현재 PC에서는 저장소 루트에서 `./scripts/build-android.ps1`로 빌드할 수 있습니다. 다른 설치 경로는 `-JdkPath`, `-SdkPath`로 지정합니다. 스크립트는 종료 시 기존 환경 변수를 복원합니다.

APK: `android/app/build/outputs/apk/debug/app-debug.apk`. 현재 앱은 환경 확인용 화면만 표시하며 촬영·통신 기능은 없습니다.

## 실기기 확인

휴대폰에서 개발자 옵션과 USB 디버깅을 켜고 연결 승인 후 아래를 실행합니다. adb가 PATH에 없으면 SDK의 `platform-tools/adb.exe` 전체 경로를 사용합니다.

```powershell
adb devices -l
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.strikezone.mobile/.MainActivity
```

위 APK 경로는 `android/` 기준입니다. 여러 기기 연결 시 `adb -s 기기ID`를 사용합니다. 앱 화면이 나타나는지 확인하고 기종·OS·빌드 결과를 기록합니다. 기본 카메라 앱의 슬로모션 메뉴 지원만으로 자체 앱의 고속 촬영 가능 여부를 확정하지 않습니다. 향후 Camera2의 high-speed 지원과 해상도별 FPS 범위를 확인하고 실제 녹화 결과를 검증해야 합니다.

## 검증 기록

[환경 검증 기록](environment-validation.md)에 실제 확인한 결과만 적습니다. 다른 팀원 PC와 실기기 확인은 각 담당자가 실행한 뒤 기록합니다.
