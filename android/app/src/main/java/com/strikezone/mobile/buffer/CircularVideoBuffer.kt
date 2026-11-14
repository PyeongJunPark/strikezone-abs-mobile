package com.strikezone.mobile.buffer

import android.media.MediaFormat
import android.util.Log
import com.strikezone.mobile.encoder.EncodedFrame
import java.util.ArrayDeque

/**
 * H.264 인코딩 프레임을 메모리에 상시 유지하는 원형 링 버퍼(Circular Buffer).
 *
 * @param bufferDurationSeconds 버퍼에 보관할 최대 영상 시간 (기본 6.0초: 4.5초 슬라이스 시 직전 선행 I-Frame 확보를 위한 안전 마진 포함)
 */
class CircularVideoBuffer(
    private val bufferDurationSeconds: Float = 6.0f
) {
    companion object {
        private const val TAG = "CircularVideoBuffer"
    }

    private val lock = Any()
    private val frameQueue = ArrayDeque<EncodedFrame>()

    /**
     * 인코더에서 전달받은 최신 MediaFormat (SPS/PPS 포함).
     */
    var outputFormat: MediaFormat? = null
        private set

    private val maxDurationUs: Long = (bufferDurationSeconds * 1_000_000L).toLong()

    /**
     * 인코더 출력 포맷 갱신 (MediaMuxer 초기화에 필수).
     */
    fun setFormat(format: MediaFormat) {
        synchronized(lock) {
            outputFormat = format
            Log.i(TAG, "MediaFormat 갱신 완료: $format")
        }
    }

    /**
     * 새로운 인코딩 프레임을 링 버퍼에 추가하고, 오래된 프레임을 자동으로 폐기.
     */
    fun addFrame(frame: EncodedFrame) {
        synchronized(lock) {
            frameQueue.addLast(frame)

            // 버퍼 보존 기간(6.0초)을 초과한 오래된 프레임 폐기
            val latestTimeUs = frameQueue.last.presentationTimeUs
            while (frameQueue.size > 1) {
                val oldestTimeUs = frameQueue.first.presentationTimeUs
                if (latestTimeUs - oldestTimeUs > maxDurationUs) {
                    frameQueue.removeFirst()
                } else {
                    break
                }
            }
        }
    }

    /**
     * 현재 버퍼에 보관 중인 영상의 시간 길이 (초 단위).
     */
    val currentDurationSeconds: Float
        get() = synchronized(lock) {
            if (frameQueue.size < 2) return@synchronized 0.0f
            val elapsedUs = frameQueue.last.presentationTimeUs - frameQueue.first.presentationTimeUs
            return@synchronized elapsedUs / 1_000_000f
        }

    /**
     * 현재 버퍼의 총 프레임 수.
     */
    val frameCount: Int
        get() = synchronized(lock) { frameQueue.size }

    /**
     * 목표 시간(기본 4.5초) 이전의 가장 가까운 Key Frame(I-Frame)부터 시작하는 프레임 리스트를 덤프.
     *
     * @param durationSeconds 덤프할 목표 영상 길이 (기본 4.5초)
     * @return 첫 번째 프레임이 반드시 Key Frame으로 정렬된 슬라이스 프레임 리스트
     */
    fun dumpSlice(durationSeconds: Float = 4.5f): List<EncodedFrame> {
        synchronized(lock) {
            if (frameQueue.isEmpty()) {
                Log.w(TAG, "링 버퍼가 비어 있어 덤프할 수 없습니다.")
                return emptyList()
            }

            val list = frameQueue.toList()
            val latestTimeUs = list.last().presentationTimeUs
            val targetCutoffTimeUs = latestTimeUs - (durationSeconds * 1_000_000L).toLong()

            // 1. targetCutoffTimeUs(4.5초 전) 이전 또는 가장 가까운 Key Frame 탐색
            var keyFrameIndex = -1
            for (i in list.indices.reversed()) {
                val f = list[i]
                if (f.isKeyFrame) {
                    keyFrameIndex = i
                    // 4.5초 이전 지점을 확보한 가장 최신의 Key Frame을 찾으면 확정
                    if (f.presentationTimeUs <= targetCutoffTimeUs) {
                        break
                    }
                }
            }

            // 2. 만약 4.5초 전 이전의 Key Frame이 없다면(앱 시작 직후 등), 버퍼 내 가장 첫 번째 Key Frame 선택
            if (keyFrameIndex == -1) {
                keyFrameIndex = list.indexOfFirst { it.isKeyFrame }
            }

            // 3. 만약 Key Frame이 전혀 없는 극단적 상황이면 전체 반환 (fallback)
            val startIndex = if (keyFrameIndex >= 0) keyFrameIndex else 0
            val slice = list.subList(startIndex, list.size)

            val sliceDuration = (slice.last().presentationTimeUs - slice.first().presentationTimeUs) / 1_000_000f
            Log.i(TAG, "덤프 슬라이스 추출 완료: 총 ${slice.size}프레임, 지속시간: ${sliceDuration}초, 시작프레임 isKeyFrame=${slice.first().isKeyFrame}")

            return slice
        }
    }

    /**
     * 버퍼 초기화.
     */
    fun clear() {
        synchronized(lock) {
            frameQueue.clear()
        }
    }
}
