package com.strikezone.mobile.buffer

import com.strikezone.mobile.encoder.EncodedFrame
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * 4.5초 원형 링 버퍼(CircularVideoBuffer)의 Key Frame 정렬 및 슬라이싱 단위 테스트.
 */
class CircularVideoBufferTest {

    private lateinit var buffer: CircularVideoBuffer

    @Before
    fun setUp() {
        // 6.0초 안전 마진 버퍼 초기화
        buffer = CircularVideoBuffer(bufferDurationSeconds = 6.0f)
    }

    private fun createDummyFrame(ptsUs: Long, isKeyFrame: Boolean): EncodedFrame {
        return EncodedFrame(
            data = ByteArray(100), // 더미 페이로드
            presentationTimeUs = ptsUs,
            flags = if (isKeyFrame) 1 else 0,
            isKeyFrame = isKeyFrame
        )
    }

    @Test
    fun testBufferOverflowEviction() {
        // 30fps 기준 7초 분량 (210프레임) 추가: 매 33,333us마다 프레임 발생
        val frameDurationUs = 33_333L
        for (i in 0 until 210) {
            val isKey = (i % 30 == 0) // 1초마다 I-Frame
            buffer.addFrame(createDummyFrame(i * frameDurationUs, isKey))
        }

        // 버퍼 보존 기간(6.0초) 초과 프레임은 삭제되어 약 6초 분량(약 180프레임 내외)만 유지되어야 함
        assertTrue(buffer.currentDurationSeconds in 5.8f..6.2f)
        assertTrue(buffer.frameCount in 175..185)
    }

    @Test
    fun testDumpSliceStartsAlwaysWithKeyFrame() {
        // 6초 분량(180프레임) 추가 (매 30프레임 = 1초마다 I-Frame)
        val frameDurationUs = 33_333L
        for (i in 0 until 180) {
            val isKey = (i % 30 == 0)
            buffer.addFrame(createDummyFrame(i * frameDurationUs, isKey))
        }

        // 4.5초 덤프 요청
        val slice = buffer.dumpSlice(4.5f)

        assertFalse("슬라이스가 비어있지 않아야 함", slice.isEmpty())
        assertTrue("슬라이스의 첫 번째 프레임은 반드시 Key Frame(I-Frame)이어야 함", slice.first().isKeyFrame)

        // 슬라이스 지속 시간은 4.5초 이상(약 4.5~5.0초)이어야 함
        val sliceDuration = (slice.last().presentationTimeUs - slice.first().presentationTimeUs) / 1_000_000f
        assertTrue("슬라이스 지속 시간($sliceDuration)은 4.5초 이상이어야 함", sliceDuration >= 4.5f)
    }

    @Test
    fun testDumpSliceWhenBufferShorterThanRequested() {
        // 앱 시작 직후 2초 분량(60프레임)만 누적된 상황
        val frameDurationUs = 33_333L
        for (i in 0 until 60) {
            val isKey = (i % 30 == 0)
            buffer.addFrame(createDummyFrame(i * frameDurationUs, isKey))
        }

        // 4.5초 덤프 요청 시 에러 없이 누적된 분량에서 첫 Key Frame부터 반환해야 함
        val slice = buffer.dumpSlice(4.5f)

        assertFalse("버퍼가 부족해도 존재하는 프레임을 반환해야 함", slice.isEmpty())
        assertTrue("첫 프레임은 Key Frame이어야 함", slice.first().isKeyFrame)
        assertEquals("버퍼의 첫 I-Frame(0번)부터 반환되어야 함", 0L, slice.first().presentationTimeUs)
    }

    @Test
    fun testPtsInversionResetsBuffer() {
        // 1. 기존에 3초 분량 프레임 적재 (PTS: 0 ~ 3초)
        val frameDurationUs = 33_333L
        for (i in 0 until 90) {
            val isKey = (i % 30 == 0)
            buffer.addFrame(createDummyFrame(i * frameDurationUs, isKey))
        }
        assertEquals(90, buffer.frameCount)

        // 2. 카메라 재시작 등으로 PTS가 0으로 리셋된 새 프레임 추가
        buffer.addFrame(createDummyFrame(0L, true))

        // 3. PTS 역전 감지 시 기존 버퍼가 리셋되어 새 프레임 1개만 남아있어야 함
        assertEquals(1, buffer.frameCount)
        assertEquals(0L, buffer.dumpSlice(4.5f).first().presentationTimeUs)
    }
}
