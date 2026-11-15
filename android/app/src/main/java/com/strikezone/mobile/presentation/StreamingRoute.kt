package com.strikezone.mobile.presentation

import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

/**
 * 스트리밍 화면의 상태 관리 및 네이티브 하드웨어 뷰(SurfaceView)를 호스팅하는 Stateful Route 컴포저블.
 *
 * 안드로이드 프레임워크 네이티브 SurfaceView와 생명주기 콜백을 처리하고,
 * 순수 Compose UI인 [StreamingScreen]으로 슬롯과 상태를 전달합니다.
 *
 * @param uiState 화면에 표시할 스트리밍 상태 정보
 * @param onSurfaceCreated 카메라 프리뷰 Surface 생성 완료 시 콜백
 * @param onSurfaceDestroyed Surface 해제 시 콜백
 * @param onHostChanged 노트북 서버 IP 입력 변경 콜백
 * @param onConnectToggleClick TCP 소켓 연결/해제 토글 버튼 클릭 콜백
 * @param onTestDumpClick 수동 4.5초 DUMP 로컬 테스트 버튼 클릭 콜백
 * @param onRetryClick 카메라 오류 후 다시 시작할 때 호출하는 콜백
 * @param modifier 레이아웃 Modifier
 */
@Composable
fun StreamingRoute(
    uiState: StreamingUiState,
    onSurfaceCreated: (Surface) -> Unit,
    onSurfaceDestroyed: () -> Unit,
    onHostChanged: (String) -> Unit,
    onConnectToggleClick: () -> Unit,
    onTestDumpClick: () -> Unit,
    onRetryClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    StreamingScreen(
        previewContent = {
            // 안드로이드 네이티브 SurfaceView를 슬롯으로 제공
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { context ->
                    SurfaceView(context).apply {
                        // Surface 버퍼는 센서 출력 크기를 사용하고, 세로 화면 회전은 SurfaceView가 처리한다.
                        holder.setFixedSize(1920, 1080)
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
        },
        uiState = uiState,
        onHostChanged = onHostChanged,
        onConnectToggleClick = onConnectToggleClick,
        onTestDumpClick = onTestDumpClick,
        onRetryClick = onRetryClick,
        modifier = modifier
    )
}
