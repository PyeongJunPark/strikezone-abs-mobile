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
import androidx.lifecycle.lifecycleScope
import com.strikezone.mobile.buffer.CircularVideoBuffer
import com.strikezone.mobile.buffer.Mp4Packager
import com.strikezone.mobile.camera.CameraCaptureManager
import com.strikezone.mobile.encoder.EncodedFrame
import com.strikezone.mobile.encoder.EncodedFrameListener
import com.strikezone.mobile.encoder.VideoEncoder
import com.strikezone.mobile.presentation.StreamingScreen
import com.strikezone.mobile.presentation.StreamingUiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * 스트존 모바일 진입점 액티비티.
 *
 * 카메라 캡처, MediaCodec 인코딩, 4.5초 원형 링 버퍼 및 MP4 패키징을 총괄합니다.
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

    // 4.5초 덤프를 위해 6.0초 안전 마진을 유지하는 원형 링 버퍼
    private val circularBuffer = CircularVideoBuffer(bufferDurationSeconds = 6.0f)
    private lateinit var mp4Packager: Mp4Packager

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
        mp4Packager = Mp4Packager(applicationContext)

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
                    },
                    onTestDumpClick = {
                        triggerManualDumpTest()
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
            circularBuffer.clear()

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
                        circularBuffer.setFormat(format)
                        Log.i(TAG, "인코더 포맷 확정 -> 링 버퍼 전달: $format")
                    }

                    override fun onFrameEncoded(frame: EncodedFrame) {
                        circularBuffer.addFrame(frame)
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
     * 인코딩된 프레임 수신 처리 (통계 및 링버퍼 UI 갱신).
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
            val bufferDuration = circularBuffer.currentDurationSeconds
            val bufferCount = circularBuffer.frameCount

            runOnUiThread {
                uiState.value = uiState.value.copy(
                    encoderStatus = String.format(
                        "인코더: %.1f FPS | 누적 %d 프레임 (IDR: %d)",
                        currentFps, totalEncodedFrames, totalKeyFrames
                    ),
                    bufferStatus = String.format(
                        "링버퍼: %.1f초 보관 중 (%d 프레임)",
                        bufferDuration, bufferCount
                    )
                )
            }
            lastFpsTimestamp = now
            framesSinceLastFps = 0
        }
    }

    /**
     * 수동 4.5초 DUMP 테스트 트리거 (백그라운드 코루틴에서 실행).
     */
    private fun triggerManualDumpTest() {
        val format = circularBuffer.outputFormat
        if (format == null) {
            Toast.makeText(this, "인코더가 아직 준비되지 않았습니다.", Toast.LENGTH_SHORT).show()
            return
        }

        lifecycleScope.launch(Dispatchers.Default) {
            try {
                val startMs = System.currentTimeMillis()
                val slice = circularBuffer.dumpSlice(4.5f)
                if (slice.isEmpty()) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "덤프할 버퍼 프레임이 부족합니다.", Toast.LENGTH_SHORT).show()
                    }
                    return@launch
                }

                val mp4File = mp4Packager.packageToFile(slice, format)
                val elapsedMs = System.currentTimeMillis() - startMs

                val fileSizeMb = mp4File.length() / (1024f * 1024f)
                val sliceDuration = (slice.last().presentationTimeUs - slice.first().presentationTimeUs) / 1_000_000f
                val isFirstKeyFrame = slice.first().isKeyFrame

                val dumpResultMsg = String.format(
                    "최근 덤프: %.1f초 클립 (%.2fMB, %d프레임, IDR시작=%b, 패키징 %dms 소요)",
                    sliceDuration, fileSizeMb, slice.size, isFirstKeyFrame, elapsedMs
                )

                Log.i(TAG, dumpResultMsg)
                withContext(Dispatchers.Main) {
                    uiState.value = uiState.value.copy(lastDumpInfo = dumpResultMsg)
                    Toast.makeText(this@MainActivity, "4.5초 MP4 덤프 성공! (${mp4File.length()} 바이트)", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Log.e(TAG, "수동 덤프 테스트 실패", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "덤프 실패: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun releasePipeline() {
        cameraManager?.stopCamera()
        cameraManager = null

        videoEncoder?.stop()
        videoEncoder = null

        circularBuffer.clear()

        runOnUiThread {
            uiState.value = uiState.value.copy(
                cameraStatus = "카메라: 정지됨",
                encoderStatus = "인코더: 정지됨",
                bufferStatus = "버퍼: 0.0초 (0 프레임)"
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
