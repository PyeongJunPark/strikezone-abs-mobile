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
import com.strikezone.mobile.network.ConnectionState
import com.strikezone.mobile.network.TcpDumpClient
import com.strikezone.mobile.network.TcpEventListener
import com.strikezone.mobile.presentation.StreamingRoute
import com.strikezone.mobile.presentation.StreamingUiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * 스트존 모바일 진입점 액티비티.
 *
 * 카메라 캡처, MediaCodec 인코딩, 4.5초 원형 링 버퍼 및 TCP DUMP 통신 파이프라인을 총괄합니다.
 */
class MainActivity : ComponentActivity(), TcpEventListener {

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

    // TCP 소켓 클라이언트 (DUMP 수신 및 MP4 송신)
    private lateinit var tcpClient: TcpDumpClient

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
        tcpClient = TcpDumpClient(listener = this)

        setContent {
            MaterialTheme {
                StreamingRoute(
                    uiState = uiState.value,
                    onSurfaceCreated = { surface ->
                        currentPreviewSurface = surface
                        checkPermissionAndStart(surface)
                    },
                    onSurfaceDestroyed = {
                        currentPreviewSurface = null
                        releasePipeline()
                    },
                    onHostChanged = { newHost ->
                        uiState.value = uiState.value.copy(serverHost = newHost)
                    },
                    onConnectToggleClick = {
                        handleConnectToggle()
                    },
                    onTestDumpClick = {
                        triggerManualDumpTest()
                    },
                    onRetryClick = {
                        currentPreviewSurface?.let { checkPermissionAndStart(it) }
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
            uiState.value = uiState.value.copy(canRetry = false)

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
            val captureManager = CameraCaptureManager(
                context = this,
                targetWidth = TARGET_WIDTH,
                targetHeight = TARGET_HEIGHT,
                targetFps = TARGET_FPS
            )
            cameraManager = captureManager
            captureManager.startCamera(
                    previewSurface = previewSurface,
                    encoderSurface = encoderSurface,
                    onStarted = {
                        runOnUiThread {
                            if (cameraManager !== captureManager) return@runOnUiThread
                            uiState.value = uiState.value.copy(
                                cameraStatus = "카메라: 1080p 30fps 스트리밍 중",
                                encoderStatus = "인코더: H.264 압축 활성화 (I-Frame 1s)",
                                canRetry = false
                            )
                        }
                    },
                    onError = { errorMsg ->
                        runOnUiThread {
                            if (cameraManager !== captureManager) return@runOnUiThread
                            releasePipeline()
                            uiState.value = uiState.value.copy(
                                cameraStatus = "카메라 오류: $errorMsg",
                                canRetry = true
                            )
                        }
                    }
                )
        } catch (e: Exception) {
            Log.e(TAG, "파이프라인 설정 실패", e)
            releasePipeline()
            uiState.value = uiState.value.copy(
                cameraStatus = "초기화 오류: ${e.message}",
                canRetry = true
            )
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
     * TCP 서버 연결/해제 토글.
     */
    private fun handleConnectToggle() {
        if (tcpClient.state == ConnectionState.CONNECTED || tcpClient.state == ConnectionState.CONNECTING) {
            tcpClient.disconnect()
        } else {
            val host = uiState.value.serverHost.trim()
            val port = uiState.value.serverPort.toIntOrNull() ?: 9999
            if (host.isEmpty()) {
                Toast.makeText(this, "서버 IP 주소를 입력하세요.", Toast.LENGTH_SHORT).show()
                return
            }
            tcpClient.connect(host, port, lifecycleScope)
        }
    }

    // -------------------------------------------------------------
    // TcpEventListener 구현부
    // -------------------------------------------------------------

    override fun onConnectionStateChanged(state: ConnectionState, message: String?) {
        runOnUiThread {
            uiState.value = uiState.value.copy(
                connectionState = state,
                connectionMessage = message ?: when (state) {
                    ConnectionState.CONNECTED -> "서버 연결 완료"
                    ConnectionState.CONNECTING -> "연결 시도 중..."
                    ConnectionState.DISCONNECTED -> "연결 끊김"
                    ConnectionState.ERROR -> "연결 오류"
                }
            )
        }
    }

    /**
     * 노트북의 DUMP 명령 수신 시 실행 (docs/protocol.md v2).
     */
    override fun onDumpRequested(durationSeconds: Float) {
        val format = circularBuffer.outputFormat
        if (format == null) {
            Log.e(TAG, "DUMP 수신했으나 인코더 포맷이 준비되지 않음")
            return
        }

        val rotationDegrees = cameraManager?.recordingRotationDegrees ?: 0

        lifecycleScope.launch(Dispatchers.Default) {
            try {
                val startMs = System.currentTimeMillis()
                // 1. 4.5초 I-Frame 정렬 슬라이스 추출
                val slice = circularBuffer.dumpSlice(durationSeconds)
                if (slice.isEmpty()) {
                    Log.w(TAG, "덤프할 프레임이 버퍼에 없음")
                    return@launch
                }

                // 2. MP4 바이너리 파일 패키징
                val mp4File = mp4Packager.packageToFile(slice, format, rotationDegrees)
                try {
                    val packageTimeMs = System.currentTimeMillis() - startMs

                    // 3. TCP 소켓을 통해 바이너리 스트리밍 송신 (4바이트 크기 + 페이로드)
                    tcpClient.sendMp4File(mp4File)

                    val totalElapsedMs = System.currentTimeMillis() - startMs
                    val sliceDuration = (slice.last().presentationTimeUs - slice.first().presentationTimeUs) / 1_000_000f
                    val sizeMb = mp4File.length() / (1024f * 1024f)

                    val msg = String.format(
                        "DUMP 송신 완료: %.1f초 (%.2fMB, %d프레임, 패키징=%dms, 총=%dms)",
                        sliceDuration, sizeMb, slice.size, packageTimeMs, totalElapsedMs
                    )
                    Log.i(TAG, msg)

                    withContext(Dispatchers.Main) {
                        uiState.value = uiState.value.copy(lastDumpInfo = msg)
                    }
                } finally {
                    if (mp4File.exists()) {
                        mp4File.delete()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "DUMP 처리 및 송신 실패", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "DUMP 전송 실패: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    override fun onPayloadSent(bytesSent: Long, elapsedMs: Long) {
        Log.i(TAG, "MP4 바이너리 전송 완료: $bytesSent 바이트 ($elapsedMs ms)")
    }

    override fun onError(errorMessage: String) {
        runOnUiThread {
            Toast.makeText(this, errorMessage, Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 수동 4.5초 DUMP 로컬 테스트 트리거.
     */
    private fun triggerManualDumpTest() {
        val format = circularBuffer.outputFormat
        val rotationDegrees = cameraManager?.recordingRotationDegrees ?: 0
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

                val mp4File = mp4Packager.packageToFile(slice, format, rotationDegrees)
                try {
                    val elapsedMs = System.currentTimeMillis() - startMs

                    val fileSizeMb = mp4File.length() / (1024f * 1024f)
                    val sliceDuration = (slice.last().presentationTimeUs - slice.first().presentationTimeUs) / 1_000_000f
                    val isFirstKeyFrame = slice.first().isKeyFrame

                    val dumpResultMsg = String.format(
                        "로컬 덤프: %.1f초 클립 (%.2fMB, %d프레임, IDR=%b, %dms)",
                        sliceDuration, fileSizeMb, slice.size, isFirstKeyFrame, elapsedMs
                    )

                    Log.i(TAG, dumpResultMsg)
                    withContext(Dispatchers.Main) {
                        uiState.value = uiState.value.copy(lastDumpInfo = dumpResultMsg)
                        Toast.makeText(this@MainActivity, "로컬 덤프 생성 완료! (${mp4File.length()} 바이트)", Toast.LENGTH_SHORT).show()
                    }
                } finally {
                    // 수동 테스트 확인 후 캐시 저장소 누수 방지를 위해 임시 파일 삭제
                    if (mp4File.exists()) {
                        mp4File.delete()
                    }
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
        tcpClient.disconnect()

        cameraManager?.stopCamera()
        cameraManager = null

        videoEncoder?.stop()
        videoEncoder = null

        circularBuffer.clear()

        // 세션 재시작 시 통계 왜곡 방지를 위한 카운터 리셋
        totalEncodedFrames = 0L
        totalKeyFrames = 0L
        framesSinceLastFps = 0
        lastFpsTimestamp = System.currentTimeMillis()

        runOnUiThread {
            uiState.value = uiState.value.copy(
                cameraStatus = "카메라: 정지됨",
                encoderStatus = "인코더: 정지됨",
                bufferStatus = "버퍼: 0.0초 (0 프레임)",
                canRetry = false
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
