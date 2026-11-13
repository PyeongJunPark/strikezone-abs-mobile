package com.strikezone.mobile

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaFormat
import android.os.Bundle
import android.util.Log
import android.view.Surface
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.core.content.ContextCompat
import com.strikezone.mobile.camera.CameraCaptureManager
import com.strikezone.mobile.encoder.EncodedFrame
import com.strikezone.mobile.encoder.EncodedFrameListener
import com.strikezone.mobile.encoder.VideoEncoder
import com.strikezone.mobile.presentation.StreamingScreen
import com.strikezone.mobile.presentation.StreamingUiState

/**
 * 스트존 모바일 진입점 액티비티.
 *
 * 안드로이드 생명주기 및 카메라·인코더 파이프라인의 오케스트레이션을 총괄합니다.
 */
class MainActivity : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivity"
        private const val TARGET_WIDTH = 1920
        private const val TARGET_HEIGHT = 1080
        private const val TARGET_FPS = 30
    }

    private var videoEncoder: VideoEncoder? = null
    private var cameraManager: CameraCaptureManager? = null
    private var currentPreviewSurface: Surface? = null

    private var totalEncodedFrames = 0L
    private var totalKeyFrames = 0L
    private var lastFpsTimestamp = System.currentTimeMillis()
    private var framesSinceLastFps = 0

    // Presentation 상태 홀더
    private val uiState = mutableStateOf(StreamingUiState())

    // 카메라 권한 요청 콜백
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            currentPreviewSurface?.let { setupCameraPipeline(it) }
        } else {
            Toast.makeText(this, "카메라 권한이 필요합니다.", Toast.LENGTH_LONG).show()
            uiState.value = uiState.value.copy(cameraStatus = "카메라: 권한 거부됨")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            MaterialTheme {
                StreamingScreen(
                    uiState = uiState.value,
                    onSurfaceCreated = { surface ->
                        currentPreviewSurface = surface
                        checkPermissionAndStart(surface)
                    },
                    onSurfaceDestroyed = {
                        currentPreviewSurface = null
                        releasePipeline()
                    }
                )
            }
        }
    }

    private fun checkPermissionAndStart(surface: Surface) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            setupCameraPipeline(surface)
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    /**
     * VideoEncoder 및 CameraCaptureManager 파이프라인 구성.
     */
    private fun setupCameraPipeline(previewSurface: Surface) {
        if (!previewSurface.isValid) {
            Log.w(TAG, "프리뷰 Surface가 유효하지 않음")
            return
        }

        try {
            // 1. MediaCodec 1080p 30fps H.264 인코더 시작
            videoEncoder = VideoEncoder(
                width = TARGET_WIDTH,
                height = TARGET_HEIGHT,
                fps = TARGET_FPS,
                bitrate = 12_000_000,
                iFrameIntervalSeconds = 1
            ).apply {
                setListener(object : EncodedFrameListener {
                    override fun onOutputFormatChanged(format: MediaFormat) {
                        Log.i(TAG, "인코더 포맷 확정: $format")
                    }

                    override fun onFrameEncoded(frame: EncodedFrame) {
                        onEncodedFrameReceived(frame)
                    }
                })
                start()
            }

            val encoderSurface = videoEncoder?.inputSurface
            if (encoderSurface == null || !encoderSurface.isValid) {
                throw IllegalStateException("인코더 InputSurface 생성 실패")
            }

            // 2. Camera2 듀얼 Surface 캡처 시작 (프리뷰 + 인코더)
            cameraManager = CameraCaptureManager(
                context = this,
                targetWidth = TARGET_WIDTH,
                targetHeight = TARGET_HEIGHT,
                targetFps = TARGET_FPS
            ).apply {
                startCamera(
                    previewSurface = previewSurface,
                    encoderSurface = encoderSurface,
                    onStarted = {
                        runOnUiThread {
                            uiState.value = uiState.value.copy(
                                cameraStatus = "카메라: 1080p 30fps 스트리밍 중",
                                encoderStatus = "인코더: H.264 압축 활성화 (I-Frame 1s)"
                            )
                        }
                    },
                    onError = { errorMsg ->
                        runOnUiThread {
                            uiState.value = uiState.value.copy(cameraStatus = "카메라 오류: $errorMsg")
                        }
                    }
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "파이프라인 설정 실패", e)
            uiState.value = uiState.value.copy(cameraStatus = "초기화 오류: ${e.message}")
        }
    }

    /**
     * 인코딩된 프레임 수신 처리 (통계 및 UI 갱신).
     */
    private fun onEncodedFrameReceived(frame: EncodedFrame) {
        totalEncodedFrames++
        if (frame.isKeyFrame) totalKeyFrames++
        framesSinceLastFps++

        val now = System.currentTimeMillis()
        val elapsed = now - lastFpsTimestamp

        // 1초마다 통계 및 UI 갱신
        if (elapsed >= 1000) {
            val currentFps = (framesSinceLastFps * 1000f / elapsed)
            val totalSeconds = totalEncodedFrames / TARGET_FPS.toFloat()

            runOnUiThread {
                uiState.value = uiState.value.copy(
                    encoderStatus = String.format(
                        "인코더: %.1f FPS | 누적 %d 프레임 (IDR: %d)",
                        currentFps, totalEncodedFrames, totalKeyFrames
                    ),
                    bufferStatus = String.format(
                        "상시 인코딩 경과: %.1f초 (3단계 링버퍼 대기)",
                        totalSeconds
                    )
                )
            }
            lastFpsTimestamp = now
            framesSinceLastFps = 0
        }
    }

    private fun releasePipeline() {
        cameraManager?.stopCamera()
        cameraManager = null

        videoEncoder?.stop()
        videoEncoder = null

        runOnUiThread {
            uiState.value = uiState.value.copy(
                cameraStatus = "카메라: 정지됨",
                encoderStatus = "인코더: 정지됨"
            )
        }
    }

    override fun onResume() {
        super.onResume()
        currentPreviewSurface?.let { surface ->
            if (surface.isValid && cameraManager == null) {
                checkPermissionAndStart(surface)
            }
        }
    }

    override fun onPause() {
        super.onPause()
        releasePipeline()
    }

    override fun onDestroy() {
        super.onDestroy()
        releasePipeline()
    }
}
