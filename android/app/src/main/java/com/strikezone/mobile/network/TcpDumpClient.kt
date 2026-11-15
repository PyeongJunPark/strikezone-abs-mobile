package com.strikezone.mobile.network

import android.util.Log
import kotlinx.coroutines.*
import java.io.*
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

/**
 * TCP 연결 상태 열거형.
 */
enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    ERROR
}

/**
 * TCP 통신 이벤트 리스너 인터페이스.
 */
interface TcpEventListener {
    /** 연결 상태 변경 시 호출 */
    fun onConnectionStateChanged(state: ConnectionState, message: String? = null)

    /** 노트북으로부터 DUMP 명령 수신 시 호출 */
    fun onDumpRequested(durationSeconds: Float)

    /** MP4 바이너리 전송 완료 시 호출 */
    fun onPayloadSent(bytesSent: Long, elapsedMs: Long)

    /** 통신 오류 발생 시 호출 */
    fun onError(errorMessage: String)
}

/**
 * 노트북과 통신하며 DUMP 제어 명령을 수신하고 4.5초 MP4 비디오 스트림을 송신하는 TCP 클라이언트.
 *
 * 규격 준수: docs/protocol.md v2
 */
class TcpDumpClient(
    private val listener: TcpEventListener
) {
    companion object {
        private const val TAG = "TcpDumpClient"
        private const val CONNECT_TIMEOUT_MS = 3000
    }

    private var socket: Socket? = null
    private var dataOutputStream: DataOutputStream? = null
    private var reader: BufferedReader? = null

    private val isRunning = AtomicBoolean(false)
    private var clientJob: Job? = null
    private val sendLock = Any()

    var state: ConnectionState = ConnectionState.DISCONNECTED
        private set(value) {
            field = value
        }

    /**
     * 노트북의 수신 서버(기본 9999 포트)로 TCP 연결 시작.
     */
    fun connect(host: String, port: Int = 9999, scope: CoroutineScope) {
        if (state == ConnectionState.CONNECTED || state == ConnectionState.CONNECTING) return

        clientJob?.cancel()
        clientJob = scope.launch(Dispatchers.IO) {
            updateState(ConnectionState.CONNECTING, "서버($host:$port) 연결 시도 중...")
            try {
                val newSocket = Socket()
                newSocket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
                newSocket.tcpNoDelay = true // 지연 최소화 (Nagle 알고리즘 비활성화)
                newSocket.keepAlive = true

                socket = newSocket
                dataOutputStream = DataOutputStream(BufferedOutputStream(newSocket.getOutputStream()))
                reader = BufferedReader(InputStreamReader(newSocket.getInputStream(), Charsets.US_ASCII))

                isRunning.set(true)
                updateState(ConnectionState.CONNECTED, "서버($host:$port) 연결 완료")
                Log.i(TAG, "노트북 서버 연결 성공: $host:$port")

                // 수신 루프 실행
                receiveLoop()
            } catch (e: Exception) {
                Log.e(TAG, "소켓 연결 실패", e)
                cleanup()
                updateState(ConnectionState.ERROR, "연결 실패: ${e.message}")
            }
        }
    }

    /**
     * 노트북으로부터 줄바꿈(\n) 단위의 ASCII 제어 명령을 지속적으로 수신.
     */
    private suspend fun receiveLoop() = withContext(Dispatchers.IO) {
        val currentReader = reader ?: return@withContext
        try {
            while (isRunning.get() && currentReader.ready() || isRunning.get()) {
                val line = currentReader.readLine() ?: break // 소켓 정상 종료 시 null
                val trimmed = line.trim()
                if (trimmed.isEmpty()) continue

                Log.i(TAG, "서버 명령 수신: $trimmed")
                handleCommand(trimmed)
            }
        } catch (e: Exception) {
            if (isRunning.get()) {
                Log.w(TAG, "수신 루프 예외: ${e.message}")
                updateState(ConnectionState.DISCONNECTED, "서버와의 연결이 끊어졌습니다.")
            }
        } finally {
            cleanup()
        }
    }

    /**
     * DUMP 명령 파싱. 예: "DUMP 4.5" -> 4.5초
     */
    private fun handleCommand(cmd: String) {
        val parts = cmd.split("\\s+".toRegex())
        if (parts.isNotEmpty() && parts[0].equals("DUMP", ignoreCase = true)) {
            val seconds = parts.getOrNull(1)?.toFloatOrNull() ?: 4.5f
            listener.onDumpRequested(seconds)
        } else {
            Log.w(TAG, "알 수 없는 명령: $cmd")
        }
    }

    /**
     * MP4 파일을 protocol.md v2 패킷 규격에 맞춰 전송.
     *
     * [Payload Size (4 Bytes Big-Endian uint32)] + [MP4 Payload (N Bytes)]
     */
    fun sendMp4File(file: File) {
        val output = dataOutputStream
        if (socket == null || output == null || !isRunning.get()) {
            listener.onError("서버에 연결되어 있지 않아 전송할 수 없습니다.")
            return
        }

        synchronized(sendLock) {
            val startMs = System.currentTimeMillis()
            val fileSize = file.length()
            if (fileSize > Int.MAX_VALUE) {
                listener.onError("파일 크기가 너무 큽니다.")
                return
            }

            try {
                // 1. 헤더: 4바이트 Big-Endian UInt32 (Java writeInt는 Big-Endian 4바이트)
                output.writeInt(fileSize.toInt())

                // 2. 페이로드: MP4 비디오 바이너리 스트리밍 (64KB 버퍼)
                val buffer = ByteArray(64 * 1024)
                var bytesSent = 0L

                FileInputStream(file).use { fis ->
                    var bytesRead: Int
                    while (fis.read(buffer).also { bytesRead = it } != -1) {
                        output.write(buffer, 0, bytesRead)
                        bytesSent += bytesRead
                    }
                }

                output.flush() // 즉시 전송 완료 보장
                val elapsedMs = System.currentTimeMillis() - startMs
                Log.i(TAG, "MP4 바이너리 스트리밍 완료: $bytesSent 바이트 ($elapsedMs ms 소요)")
                listener.onPayloadSent(bytesSent, elapsedMs)
            } catch (e: Exception) {
                Log.e(TAG, "MP4 전송 실패", e)
                listener.onError("전송 오류: ${e.message}")
                disconnect()
            }
        }
    }

    /**
     * 소켓 연결 해제 및 자원 정리.
     */
    fun disconnect() {
        isRunning.set(false)
        clientJob?.cancel()
        clientJob = null
        cleanup()
        updateState(ConnectionState.DISCONNECTED, "연결 해제됨")
    }

    private fun cleanup() {
        try {
            reader?.close()
            dataOutputStream?.close()
            socket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "소켓 정리 중 경고", e)
        } finally {
            reader = null
            dataOutputStream = null
            socket = null
        }
    }

    private fun updateState(newState: ConnectionState, message: String) {
        state = newState
        listener.onConnectionStateChanged(newState, message)
    }
}
