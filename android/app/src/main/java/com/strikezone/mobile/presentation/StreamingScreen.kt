package com.strikezone.mobile.presentation

import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView

/**
 * 풀스크린 카메라 프리뷰와 상단 반투명 모니터링 오버레이 패널을 표시하는 Composable 화면.
 *
 * @param uiState 화면에 표시할 스트리밍 상태 정보
 * @param onSurfaceCreated 카메라 프리뷰 Surface 생성 완료 시 콜백
 * @param onSurfaceDestroyed Surface 해제 시 콜백
 */
@Composable
fun StreamingScreen(
    uiState: StreamingUiState,
    onSurfaceCreated: (Surface) -> Unit,
    onSurfaceDestroyed: () -> Unit,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color.Black)
    ) {
        // 카메라 프리뷰 SurfaceView 렌더링
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                SurfaceView(context).apply {
                    holder.addCallback(object : SurfaceHolder.Callback {
                        override fun surfaceCreated(holder: SurfaceHolder) {
                            onSurfaceCreated(holder.surface)
                        }

                        override fun surfaceChanged(
                            holder: SurfaceHolder,
                            format: Int,
                            width: Int,
                            height: Int
                        ) {}

                        override fun surfaceDestroyed(holder: SurfaceHolder) {
                            onSurfaceDestroyed()
                        }
                    })
                }
            }
        )

        // 상단 반투명 모니터링 카드 오버레이
        StatusOverlayCard(
            uiState = uiState,
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .align(Alignment.TopCenter)
        )
    }
}

/**
 * 상단 스트리밍 및 버퍼 상태 오버레이 카드 컴포넌트.
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
            Text(
                text = "스트존 모바일 (ABS)",
                color = Color.White,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(6.dp))
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
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun StatusOverlayCardPreview() {
    StatusOverlayCard(
        uiState = StreamingUiState(
            cameraStatus = "카메라: 1080p 30fps 스트리밍 중",
            encoderStatus = "인코더: 30.0 FPS | 누적 150 프레임 (IDR: 5)",
            bufferStatus = "상시 인코딩 경과: 5.0초 (3단계 링버퍼 대기)"
        ),
        modifier = Modifier.padding(16.dp)
    )
}
