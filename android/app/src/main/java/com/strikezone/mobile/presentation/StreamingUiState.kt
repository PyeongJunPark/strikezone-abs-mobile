package com.strikezone.mobile.presentation

import com.strikezone.mobile.network.ConnectionState

/**
 * 실시간 스트리밍 UI 상태 데이터 모델.
 *
 * @property cameraStatus 카메라 스트리밍 및 해상도/FPS 상태
 * @property encoderStatus H.264 인코더 압축 및 실시간 FPS/Key Frame 통계
 * @property bufferStatus 링버퍼 적재 시간 및 총 프레임 수
 * @property serverHost 노트북 TCP 서버 IP 주소
 * @property serverPort 노트북 TCP 서버 포트
 * @property connectionState 현재 TCP 소켓 연결 상태
 * @property connectionMessage 연결 상태 상세 설명
 * @property lastDumpInfo 최근 수행한 덤프 결과 정보 (파일 크기, 소요 시간 등)
 * @property canRetry 카메라 초기화 또는 연결 실패 후 재시작 버튼을 표시할지 여부
 */
data class StreamingUiState(
    val cameraStatus: String = "카메라: 초기화 대기 중",
    val encoderStatus: String = "인코더: 1080p 30fps H.264 준비 중",
    val bufferStatus: String = "버퍼: 0.0초 (0 프레임)",
    val serverHost: String = "192.168.43.1",
    val serverPort: String = "9999",
    val connectionState: ConnectionState = ConnectionState.DISCONNECTED,
    val connectionMessage: String = "서버 미연결",
    val lastDumpInfo: String? = null,
    val canRetry: Boolean = false
)
