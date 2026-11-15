package com.strikezone.mobile.camera

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.*
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.util.Range
import android.view.Surface
import android.view.SurfaceHolder
import android.view.WindowManager

/**
 * Camera2 API 기반의 고성능 무복사(Zero-Copy) 카메라 캡처 매니저.
 *
 * 화면 프리뷰 Surface와 MediaCodec 인코더 InputSurface로 1080p 30fps 스트림을 동시에 멀티캐스트합니다.
 */
class CameraCaptureManager(
    private val context: Context,
    private val targetWidth: Int = 1920,
    private val targetHeight: Int = 1080,
    private val targetFps: Int = 30
) {
    companion object {
        private const val TAG = "CameraCaptureManager"
    }

    private val cameraManager: CameraManager =
        context.getSystemService(Context.CAMERA_SERVICE) as CameraManager

    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var cameraThread: HandlerThread? = null
    private var cameraHandler: Handler? = null

    private var isSessionActive = false
    @Volatile private var isCameraRequested = false

    var recordingRotationDegrees: Int = 0
        private set

    /**
     * 카메라 백그라운드 스레드 시작.
     */
    private fun startBackgroundThread() {
        cameraThread = HandlerThread("CameraBackgroundThread").apply { start() }
        cameraHandler = Handler(cameraThread!!.looper)
    }

    /**
     * 카메라 백그라운드 스레드 정지.
     */
    private fun stopBackgroundThread() {
        cameraThread?.quitSafely()
        try {
            // HandlerThread 콜백 내부에서 stopCamera() 호출 시 데드락(Deadlock) 방지
            if (Thread.currentThread() != cameraThread) {
                cameraThread?.join()
            }
            cameraThread = null
            cameraHandler = null
        } catch (e: InterruptedException) {
            Log.e(TAG, "카메라 스레드 중지 중 인터럽트", e)
        }
    }

    /**
     * 후면 카메라 ID 검색.
     */
    private fun getBackCameraId(): String {
        val cameraIds = cameraManager.cameraIdList
        if (cameraIds.isEmpty()) {
            throw IllegalStateException("사용 가능한 카메라 장치를 찾을 수 없습니다.")
        }
        for (id in cameraIds) {
            val characteristics = cameraManager.getCameraCharacteristics(id)
            val facing = characteristics.get(CameraCharacteristics.LENS_FACING)
            if (facing == CameraCharacteristics.LENS_FACING_BACK) {
                return id
            }
        }
        return cameraIds[0]
    }

    /**
     * 30fps 목표를 위한 가장 적합한 FPS Range 탐색.
     */
    private fun findOptimalFpsRange(characteristics: CameraCharacteristics): Range<Int> {
        val ranges = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)
            ?: return Range(targetFps, targetFps)

        // 1순위: [30, 30] 고정 범위 탐색
        for (range in ranges) {
            if (range.lower == targetFps && range.upper == targetFps) {
                return range
            }
        }
        // 2순위: 상한이 30인 범위 탐색
        for (range in ranges) {
            if (range.upper == targetFps) {
                return range
            }
        }
        return ranges.last()
    }

    /**
     * 카메라를 열고 프리뷰 및 인코더 Surface로 캡처 세션 시작.
     *
     * @param previewSurface 화면 프리뷰용 Surface (SurfaceView)
     * @param encoderSurface MediaCodec H.264 인코더 입력 Surface
     * @param onStarted 세션 시작 성공 콜백
     * @param onError 오류 발생 콜백
     */
    @SuppressLint("MissingPermission")
    fun startCamera(
        previewSurface: Surface,
        encoderSurface: Surface,
        onStarted: () -> Unit = {},
        onError: (String) -> Unit = {}
    ) {
        if (isSessionActive) return

        val cameraId = getBackCameraId()
        val characteristics = cameraManager.getCameraCharacteristics(cameraId)
        val selectedFpsRange = findOptimalFpsRange(characteristics)

        // SurfaceView 버퍼는 회전 전의 카메라 출력 크기를 사용해야 한다.
        val streamMap = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
        val supportedSizes = streamMap?.getOutputSizes(SurfaceHolder::class.java) ?: emptyArray()
        val isResolutionSupported = supportedSizes.any {
            it.width == targetWidth && it.height == targetHeight
        }
        if (!isResolutionSupported) {
            throw IllegalStateException("카메라가 ${targetWidth}x${targetHeight} 출력을 지원하지 않습니다.")
        }

        @Suppress("DEPRECATION")
        val displayRotation = (context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.rotation
        val displayRotationDegrees = when (displayRotation) {
            Surface.ROTATION_90 -> 90
            Surface.ROTATION_180 -> 180
            Surface.ROTATION_270 -> 270
            else -> 0
        }
        val sensorRotationDegrees = characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0
        val sign = if (characteristics.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_FRONT) 1 else -1
        recordingRotationDegrees = (sensorRotationDegrees - displayRotationDegrees * sign + 360) % 360
        Log.i(TAG, "선택된 카메라 ID: $cameraId, FPS 범위: $selectedFpsRange, 목표 해상도: ${targetWidth}x${targetHeight}, 영상 회전: $recordingRotationDegrees")

        try {
            isCameraRequested = true
            startBackgroundThread()
            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    if (!isCameraRequested) {
                        camera.close()
                        return
                    }
                    cameraDevice = camera
                    createCaptureSession(camera, previewSurface, encoderSurface, selectedFpsRange, onStarted, onError)
                }

                override fun onDisconnected(camera: CameraDevice) {
                    Log.w(TAG, "카메라 연결 끊김")
                    stopCamera()
                    onError("카메라 연결이 끊겼습니다.")
                }

                override fun onError(camera: CameraDevice, error: Int) {
                    val msg = "카메라 열기 실패 (오류 코드: $error)"
                    Log.e(TAG, msg)
                    stopCamera()
                    onError(msg)
                }
            }, cameraHandler)
        } catch (e: Exception) {
            Log.e(TAG, "카메라 시작 예외", e)
            stopCamera()
            onError(e.message ?: "카메라 초기화 실패")
        }
    }

    /**
     * 두 Surface를 타깃으로 하는 캡처 세션 생성.
     */
    @Suppress("DEPRECATION")
    private fun createCaptureSession(
        camera: CameraDevice,
        previewSurface: Surface,
        encoderSurface: Surface,
        fpsRange: Range<Int>,
        onStarted: () -> Unit,
        onError: (String) -> Unit
    ) {
        try {
            val targets = listOf(previewSurface, encoderSurface)

            camera.createCaptureSession(targets, object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    if (!isCameraRequested || cameraDevice == null) {
                        session.close()
                        return
                    }
                    captureSession = session

                    try {
                        // 비디오 레코딩 템플릿(안정적인 노출과 FPS 유지)
                        val requestBuilder = camera.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
                            addTarget(previewSurface)
                            addTarget(encoderSurface)

                            // 30fps 고정 및 연속 오토포커스 설정
                            set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                            set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
                            set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fpsRange)
                        }

                        session.setRepeatingRequest(requestBuilder.build(), null, cameraHandler)
                        isSessionActive = true
                        Log.i(TAG, "Camera2 듀얼 타깃 캡처 세션 시작 완료 (프리뷰 + 인코더)")
                        onStarted()
                    } catch (e: Exception) {
                        Log.e(TAG, "세션 반복 요청 설정 실패", e)
                        onError("캡처 요청 실패: ${e.message}")
                    }
                }

                override fun onConfigureFailed(session: CameraCaptureSession) {
                    Log.e(TAG, "Camera2 세션 구성 실패")
                    onError("카메라 세션 구성 실패")
                }
            }, cameraHandler)
        } catch (e: Exception) {
            Log.e(TAG, "캡처 세션 생성 예외", e)
            onError("캡처 세션 생성 예외: ${e.message}")
        }
    }

    /**
     * 카메라 및 세션 자원 완전 해제.
     */
    fun stopCamera() {
        isCameraRequested = false
        isSessionActive = false
        try {
            captureSession?.close()
            captureSession = null

            cameraDevice?.close()
            cameraDevice = null
        } catch (e: Exception) {
            Log.w(TAG, "카메라 종료 중 경고", e)
        } finally {
            stopBackgroundThread()
            Log.i(TAG, "CameraCaptureManager 자원 해제 완료")
        }
    }
}
