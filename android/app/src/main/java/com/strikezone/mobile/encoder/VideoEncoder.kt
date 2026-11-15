package com.strikezone.mobile.encoder

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.view.Surface
import java.nio.ByteBuffer

/**
 * 인코딩된 개별 H.264 프레임(NAL Unit) 데이터 모델.
 *
 * @property data 인코딩된 H.264 바이너리 바이트 배열
 * @property presentationTimeUs 프레임 타임스탬프 (마이크로초)
 * @property flags MediaCodec.BufferInfo 플래그 (KEY_FRAME, CODEC_CONFIG 등)
 * @property isKeyFrame 독립 디코딩 가능한 I-Frame (IDR) 여부
 */
data class EncodedFrame(
    val data: ByteArray,
    val presentationTimeUs: Long,
    val flags: Int,
    val isKeyFrame: Boolean
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as EncodedFrame
        return presentationTimeUs == other.presentationTimeUs && flags == other.flags
    }

    override fun hashCode(): Int {
        var result = presentationTimeUs.hashCode()
        result = 31 * result + flags
        return result
    }
}

/**
 * 인코더 출력 이벤트 리스너 인터페이스.
 */
interface EncodedFrameListener {
    /**
     * 인코더 초기화 또는 출력 포맷 확정 시 호출 (MediaMuxer 트랙 추가 시 필수).
     */
    fun onOutputFormatChanged(format: MediaFormat)

    /**
     * 개별 프레임 인코딩 완료 시 호출.
     */
    fun onFrameEncoded(frame: EncodedFrame)
}

/**
 * Camera2 Surface로부터 영상을 입력받아 1080p 30fps H.264로 상시 압축하는 하드웨어 인코더.
 */
class VideoEncoder(
    private val width: Int = 1920,
    private val height: Int = 1080,
    private val fps: Int = 30,
    private val bitrate: Int = 12_000_000, // 12 Mbps
    private val iFrameIntervalSeconds: Int = 1 // 1초 주기 I-Frame (IDR)
) {
    companion object {
        private const val TAG = "VideoEncoder"
        private const val MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_AVC
    }

    private var mediaCodec: MediaCodec? = null
    private var handlerThread: HandlerThread? = null
    private var codecHandler: Handler? = null

    /**
     * Camera2 프리뷰 세션에 바인딩할 인코더 입력 Surface.
     */
    var inputSurface: Surface? = null
        private set

    private var listener: EncodedFrameListener? = null
    var isRunning: Boolean = false
        private set

    /**
     * 리스너 등록.
     */
    fun setListener(listener: EncodedFrameListener) {
        this.listener = listener
    }

    /**
     * 인코더 초기화 및 시작.
     */
    fun start() {
        if (isRunning) return

        try {
            // 백그라운드 핸들러 스레드 시작 (인코더 콜백 전용)
            handlerThread = HandlerThread("VideoEncoderThread").apply { start() }
            codecHandler = Handler(handlerThread!!.looper)

            val format = MediaFormat.createVideoFormat(MIME_TYPE, width, height).apply {
                setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
                setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
                setInteger(MediaFormat.KEY_FRAME_RATE, fps)
                // 1초 주기로 Key Frame(IDR) 생성 보장 (슬라이싱 시 선행 I-Frame 정렬용)
                setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, iFrameIntervalSeconds)
            }

            mediaCodec = MediaCodec.createEncoderByType(MIME_TYPE).apply {
                setCallback(createCodecCallback(), codecHandler)
                configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
                inputSurface = createInputSurface()
                start()
            }

            isRunning = true
            Log.i(TAG, "MediaCodec H.264 인코더 시작 완료: ${width}x${height} @ ${fps}fps, I-Frame interval=${iFrameIntervalSeconds}s")
        } catch (e: Exception) {
            Log.e(TAG, "인코더 시작 실패", e)
            stop()
            throw e
        }
    }

    /**
     * 인코더 콜백 생성.
     */
    private fun createCodecCallback() = object : MediaCodec.Callback() {
        override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
            // Surface 입력 모드이므로 사용되지 않음
        }

        override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
            try {
                val outputBuffer: ByteBuffer? = codec.getOutputBuffer(index)
                if (outputBuffer != null && info.size > 0) {
                    val isCodecConfig = (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0
                    if (isCodecConfig) {
                        // SPS/PPS 코덱 설정 데이터는 onOutputFormatChanged를 통해 MediaFormat으로 수신되므로 프레임 큐 적재 제외
                        codec.releaseOutputBuffer(index, false)
                        return
                    }

                    outputBuffer.position(info.offset)
                    outputBuffer.limit(info.offset + info.size)

                    val isKeyFrame = (info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0

                    val data = ByteArray(info.size)
                    outputBuffer.get(data)

                    val encodedFrame = EncodedFrame(
                        data = data,
                        presentationTimeUs = info.presentationTimeUs,
                        flags = info.flags,
                        isKeyFrame = isKeyFrame
                    )

                    listener?.onFrameEncoded(encodedFrame)
                }
                codec.releaseOutputBuffer(index, false)
            } catch (e: Exception) {
                Log.e(TAG, "출력 버퍼 처리 중 오류", e)
            }
        }

        override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
            Log.e(TAG, "MediaCodec 오류 발생: ${e.diagnosticInfo}", e)
        }

        override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
            Log.i(TAG, "MediaCodec 출력 포맷 변경 확정: $format")
            listener?.onOutputFormatChanged(format)
        }
    }

    /**
     * 인코더 정지 및 자원 해제.
     */
    fun stop() {
        isRunning = false
        try {
            mediaCodec?.apply {
                stop()
                release()
            }
        } catch (e: Exception) {
            Log.w(TAG, "인코더 종료 중 경고", e)
        } finally {
            mediaCodec = null
            inputSurface?.release()
            inputSurface = null

            handlerThread?.quitSafely()
            handlerThread = null
            codecHandler = null
            Log.i(TAG, "MediaCodec H.264 인코더 자원 해제 완료")
        }
    }
}
