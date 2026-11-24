package com.strikezone.mobile.buffer

import android.content.Context
import android.media.MediaCodec
import android.media.MediaFormat
import android.media.MediaMuxer
import android.util.Log
import com.strikezone.mobile.encoder.EncodedFrame
import java.io.File
import java.nio.ByteBuffer

/**
 * 링 버퍼에서 슬라이스된 EncodedFrame 리스트를 H.264 MP4 비디오 파일로 패키징하는 도구.
 */
class Mp4Packager(private val context: Context) {

    companion object {
        private const val TAG = "Mp4Packager"
    }

    /**
     * 프레임 리스트를 MP4 파일로 패키징하고 결과 바이트 배열을 반환.
     *
     * @param frames 패키징할 H.264 프레임 리스트 (첫 프레임은 Key Frame이어야 함)
     * @param format 인코더의 MediaFormat (SPS/PPS 포함)
     * @param rotationDegrees 센서 출력 영상을 바로 세우기 위한 시계 방향 회전 각도
     * @return 생성된 MP4 바이너리 ByteArray
     */
    fun packageToMp4(frames: List<EncodedFrame>, format: MediaFormat, rotationDegrees: Int): ByteArray {
        val outputFile = packageToFile(frames, format, rotationDegrees)
        try {
            return outputFile.readBytes()
        } finally {
            if (outputFile.exists()) {
                outputFile.delete()
            }
        }
    }

    /**
     * 프레임 리스트를 임시 캐시 디렉터리의 MP4 파일로 패키징.
     *
     * @param frames 패키징할 H.264 프레임 리스트
     * @param format 인코더의 MediaFormat
     * @param rotationDegrees 센서 출력 영상을 바로 세우기 위한 시계 방향 회전 각도
     * @return 생성된 MP4 File 객체
     */
    fun packageToFile(frames: List<EncodedFrame>, format: MediaFormat, rotationDegrees: Int): File {
        if (frames.isEmpty()) {
            throw IllegalArgumentException("패키징할 프레임이 없습니다.")
        }

        val startTime = System.currentTimeMillis()
        // I/O 경합 및 덮어쓰기 방지를 위해 유니크한 임시 파일 생성
        val tempFile = File.createTempFile("dump_", ".mp4", context.cacheDir)

        var muxer: MediaMuxer? = null
        try {
            muxer = MediaMuxer(tempFile.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            // 디코더가 프리뷰와 동일한 방향으로 영상을 바로 세우도록 회전 메타데이터를 기록한다.
            muxer.setOrientationHint(rotationDegrees)
            val trackIndex = muxer.addTrack(format)
            muxer.start()

            val baseTimeUs = frames.first().presentationTimeUs
            var lastPtsUs = -1L

            val bufferInfo = MediaCodec.BufferInfo()

            for (frame in frames) {
                // 고정 크기 할당 대신 frame.data를 직접 wrap하여 1MB 버퍼 오버플로우 방지 및 무복사 처리
                val byteBuffer = ByteBuffer.wrap(frame.data)

                // 타임스탬프를 0초 기준으로 리베이싱 (백엔드 디코더 0번 프레임 정렬)
                var ptsUs = frame.presentationTimeUs - baseTimeUs
                if (ptsUs <= lastPtsUs) {
                    // PTS 역전 방지 (MediaMuxer 필수 조건)
                    ptsUs = lastPtsUs + 1000L // 최소 1ms 증가
                }
                lastPtsUs = ptsUs

                bufferInfo.set(
                    0,
                    frame.data.size,
                    ptsUs,
                    frame.flags
                )

                muxer.writeSampleData(trackIndex, byteBuffer, bufferInfo)
            }

            muxer.stop()
            val elapsedMs = System.currentTimeMillis() - startTime
            Log.i(TAG, "MP4 패키징 완료: 파일 크기=${tempFile.length()} 바이트 (${frames.size}프레임), 소요시간=${elapsedMs}ms")
            return tempFile
        } catch (e: Exception) {
            Log.e(TAG, "MP4 패키징 중 오류 발생", e)
            if (tempFile.exists()) {
                tempFile.delete()
            }
            throw e
        } finally {
            try {
                muxer?.release()
            } catch (e: Exception) {
                Log.w(TAG, "MediaMuxer release 경고", e)
            }
        }
    }
}
