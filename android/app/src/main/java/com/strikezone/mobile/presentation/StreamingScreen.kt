package com.strikezone.mobile.presentation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.strikezone.mobile.network.ConnectionState

/**
 * 100% 순수 Compose 기반의 카메라 프리뷰 오버레이 및 모니터링 화면 (Stateless).
 *
 * 안드로이드 네이티브 View(SurfaceView)에 직접 의존하지 않고 [previewContent] 슬롯을 통해
 * 카메라 프리뷰를 주입받아 렌더링하므로, IDE Preview 및 UI 테스트가 온전히 가능합니다.
 *
 * @param previewContent 카메라 프리뷰 또는 더미 배경을 렌더링할 Composable 슬롯
 * @param uiState 화면에 표시할 스트리밍 상태 정보 (카메라, 인코더, 버퍼 및 네트워크 상태)
 * @param onHostChanged 노트북 서버 IP 입력 변경 콜백
 * @param onConnectToggleClick TCP 소켓 연결/해제 토글 버튼 클릭 콜백
 * @param onTestDumpClick 수동 4.5초 DUMP 로컬 테스트 버튼 클릭 콜백
 * @param onRetryClick 카메라 오류 후 다시 시작할 때 호출하는 콜백
 * @param modifier 레이아웃 Modifier
 */
@Composable
fun StreamingScreen(
    previewContent: @Composable () -> Unit,
    uiState: StreamingUiState,
    onHostChanged: (String) -> Unit,
    onConnectToggleClick: () -> Unit,
    onTestDumpClick: () -> Unit,
    onRetryClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color.Black)
    ) {
        // 배경 프리뷰 슬롯 (실제 런타임: SurfaceView / Preview: Mock Box)
        previewContent()

        // 상단 반투명 모니터링 카드 오버레이
        StatusOverlayCard(
            uiState = uiState,
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .align(Alignment.TopCenter)
        )

        // 카메라 오류 시 재시작 버튼
        if (uiState.canRetry) {
            Button(
                onClick = onRetryClick,
                modifier = Modifier.align(Alignment.Center),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0xFFD32F2F)
                )
            ) {
                Text("카메라 다시 시작")
            }
        }

        // 하단 컨트롤 패널 (IP 입력 + 연결 버튼 + 수동 테스트)
        BottomControlPanel(
            uiState = uiState,
            onHostChanged = onHostChanged,
            onConnectToggleClick = onConnectToggleClick,
            onTestDumpClick = onTestDumpClick,
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .padding(16.dp)
        )
    }
}

/**
 * 상단 스트리밍 및 버퍼 상태 오버레이 카드 컴포넌트.
 *
 * @param uiState 스트리밍 상태 모델
 * @param modifier 레이아웃 Modifier
 */
@Composable
fun StatusOverlayCard(
    uiState: StreamingUiState,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = Color.Black.copy(alpha = 0.65f)
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "스트존 모바일 (ABS)",
                    color = Color.White,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold
                )

                // 연결 상태 배지
                ConnectionBadge(state = uiState.connectionState)
            }

            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "네트워크: ${uiState.connectionMessage}",
                color = when (uiState.connectionState) {
                    ConnectionState.CONNECTED -> Color(0xFF66FF66)
                    ConnectionState.CONNECTING -> Color(0xFFFFCC00)
                    ConnectionState.ERROR -> Color(0xFFFF6666)
                    ConnectionState.DISCONNECTED -> Color(0xFFCCCCCC)
                },
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium
            )

            Spacer(modifier = Modifier.height(3.dp))
            Text(
                text = uiState.cameraStatus,
                color = Color(0xFFDDDDDD),
                fontSize = 13.sp
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = uiState.encoderStatus,
                color = Color(0xFF99CCFF),
                fontSize = 13.sp
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = uiState.bufferStatus,
                color = Color(0xFFFFFF99),
                fontSize = 13.sp
            )

            uiState.lastDumpInfo?.let { dumpInfo ->
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = dumpInfo,
                    color = Color(0xFF88FF88),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }
    }
}

/**
 * TCP 연결 상태 표시 배지 컴포넌트.
 *
 * @param state 현재 TCP 연결 상태
 */
@Composable
fun ConnectionBadge(state: ConnectionState) {
    val (bgColor, textColor, text) = when (state) {
        ConnectionState.CONNECTED -> Triple(Color(0xFF2E7D32), Color.White, "연결됨")
        ConnectionState.CONNECTING -> Triple(Color(0xFFF57F17), Color.White, "연결 중")
        ConnectionState.ERROR -> Triple(Color(0xFFC62828), Color.White, "오류")
        ConnectionState.DISCONNECTED -> Triple(Color(0xFF424242), Color.LightGray, "대기")
    }

    Box(
        modifier = Modifier
            .background(bgColor, RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    ) {
        Text(text = text, color = textColor, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}

/**
 * 하단 연결 제어 및 수동 테스트 패널 컴포넌트.
 *
 * @param uiState 화면에 표시할 스트리밍 상태 정보
 * @param onHostChanged 노트북 서버 IP 입력 변경 콜백
 * @param onConnectToggleClick TCP 소켓 연결/해제 토글 버튼 클릭 콜백
 * @param onTestDumpClick 수동 4.5초 DUMP 로컬 테스트 버튼 클릭 콜백
 * @param modifier 레이아웃 Modifier
 */
@Composable
fun BottomControlPanel(
    uiState: StreamingUiState,
    onHostChanged: (String) -> Unit,
    onConnectToggleClick: () -> Unit,
    onTestDumpClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = Color.Black.copy(alpha = 0.70f)
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = uiState.serverHost,
                    onValueChange = onHostChanged,
                    label = { Text("노트북 IP 주소", color = Color.LightGray) },
                    singleLine = true,
                    enabled = uiState.connectionState != ConnectionState.CONNECTED,
                    modifier = Modifier.weight(1f),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = Color(0xFF64B5F6),
                        unfocusedBorderColor = Color.Gray
                    )
                )

                Spacer(modifier = Modifier.width(8.dp))

                val isConnected = uiState.connectionState == ConnectionState.CONNECTED
                Button(
                    onClick = onConnectToggleClick,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isConnected) Color(0xFFD32F2F) else Color(0xFF388E3C)
                    ),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.height(56.dp)
                ) {
                    Text(
                        text = if (isConnected) "연결 끊기" else "연결",
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            OutlinedButton(
                onClick = onTestDumpClick,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = Color(0xFF90CAF9)
                ),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text("4.5초 DUMP 수동 로컬 테스트")
            }
        }
    }
}

/**
 * 100% 순수 Compose 화면 프리뷰 (슬롯에 더미 뷰를 주입하여 카메라 없이 완전 렌더링).
 */
@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun StreamingScreenPreview() {
    StreamingScreen(
        previewContent = {
            // 카메라 대신 더미 야구장 배경을 시뮬레이션
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color(0xFF263238)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "[ 카메라 프리뷰 화면 영역 ]",
                    color = Color.Gray,
                    fontSize = 16.sp
                )
            }
        },
        uiState = StreamingUiState(
            cameraStatus = "카메라: 1080p 30fps 스트리밍 중",
            encoderStatus = "인코더: 30.0 FPS | 누적 150 프레임 (IDR: 5)",
            bufferStatus = "버퍼: 6.0초 (180 프레임 보관 중)",
            serverHost = "192.168.43.1",
            connectionState = ConnectionState.CONNECTED,
            connectionMessage = "서버(192.168.43.1:9999) 연결 완료",
            lastDumpInfo = "최근 덤프: 4.6초 클립 (5.2MB, 42ms 소요) 생성 완료"
        ),
        onHostChanged = {},
        onConnectToggleClick = {},
        onTestDumpClick = {},
        onRetryClick = {}
    )
}
