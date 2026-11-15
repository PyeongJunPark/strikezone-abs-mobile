package com.strikezone.mobile.network

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.BufferedOutputStream
import java.io.BufferedReader
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.InputStreamReader
import java.net.InetSocketAddress
import java.net.Socket

/** TCP 연결 상태. */
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, ERROR }

/** TCP 통신 이벤트 리스너. */
interface TcpEventListener {
    fun onConnectionStateChanged(state: ConnectionState, message: String? = null)
    fun onDumpRequested(durationSeconds: Float)
    fun onPayloadSent(bytesSent: Long, elapsedMs: Long)
    fun onError(errorMessage: String)
}

/** 노트북의 DUMP 명령을 수신하고 MP4 파일을 전송하는 TCP 클라이언트. */
class TcpDumpClient(private val listener: TcpEventListener) {
    companion object {
        private const val TAG = "TcpDumpClient"
        private const val CONNECT_TIMEOUT_MS = 3000
    }

    private data class Connection(
        val socket: Socket,
        val output: DataOutputStream,
        val reader: BufferedReader
    )

    private val connectionLock = Any()
    private val sendLock = Any()
    private var generation = 0L
    private var pendingSocket: Socket? = null
    private var connection: Connection? = null
    private var clientJob: Job? = null

    @Volatile
    var state: ConnectionState = ConnectionState.DISCONNECTED
        private set

    /** 연결 상태를 먼저 바꿔 연속 입력에 따른 중복 연결 작업을 막는다. */
    fun connect(host: String, port: Int = 9999, scope: CoroutineScope) {
        val job: Job
        synchronized(connectionLock) {
            if (state == ConnectionState.CONNECTED || state == ConnectionState.CONNECTING) return
            val newSocket = Socket()
            val token = ++generation
            pendingSocket = newSocket
            state = ConnectionState.CONNECTING
            listener.onConnectionStateChanged(state, "서버($host:$port) 연결 시도 중...")
            job = scope.launch(Dispatchers.IO, start = CoroutineStart.LAZY) {
                runConnection(newSocket, token, host, port)
            }
            clientJob = job
        }
        job.start()
    }

    private fun runConnection(newSocket: Socket, token: Long, host: String, port: Int) {
        try {
            newSocket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            newSocket.tcpNoDelay = true
            newSocket.keepAlive = true
            val established = Connection(
                newSocket,
                DataOutputStream(BufferedOutputStream(newSocket.getOutputStream())),
                BufferedReader(InputStreamReader(newSocket.getInputStream(), Charsets.US_ASCII))
            )
            synchronized(connectionLock) {
                if (token != generation || pendingSocket !== newSocket) return
                pendingSocket = null
                connection = established
                state = ConnectionState.CONNECTED
                listener.onConnectionStateChanged(state, "서버($host:$port) 연결 완료")
            }
            Log.i(TAG, "노트북 서버 연결 성공: $host:$port")
            receiveLoop(established, token)
        } catch (e: Exception) {
            closeSocket(newSocket)
            synchronized(connectionLock) {
                if (token == generation && pendingSocket === newSocket) {
                    pendingSocket = null
                    clientJob = null
                    state = ConnectionState.ERROR
                    listener.onConnectionStateChanged(state, "연결 실패: ${e.message}")
                }
            }
            Log.w(TAG, "소켓 연결 종료", e)
        } finally {
            closeSocket(newSocket)
        }
    }

    /** EOF와 수신 오류 모두 연결 종료로 처리하고, 이전 작업은 새 연결을 건드리지 않는다. */
    private fun receiveLoop(current: Connection, token: Long) {
        try {
            while (isCurrentConnection(current, token)) {
                val line = current.reader.readLine() ?: break
                val command = line.trim()
                if (command.isNotEmpty() && isCurrentConnection(current, token)) {
                    Log.i(TAG, "서버 명령 수신: $command")
                    handleCommand(command)
                }
            }
        } catch (e: Exception) {
            if (isCurrentConnection(current, token)) Log.w(TAG, "수신 루프 예외", e)
        } finally {
            closeSocket(current.socket)
            synchronized(connectionLock) {
                if (token == generation && connection === current) {
                    connection = null
                    clientJob = null
                    state = ConnectionState.DISCONNECTED
                    listener.onConnectionStateChanged(state, "서버와의 연결이 끊어졌습니다.")
                }
            }
        }
    }

    private fun isCurrentConnection(current: Connection, token: Long): Boolean =
        synchronized(connectionLock) { token == generation && connection === current }

    private fun handleCommand(cmd: String) {
        val parts = cmd.split("\\s+".toRegex())
        if (parts.isNotEmpty() && parts[0].equals("DUMP", ignoreCase = true)) {
            listener.onDumpRequested(parts.getOrNull(1)?.toFloatOrNull() ?: 4.5f)
        } else {
            Log.w(TAG, "알 수 없는 명령: $cmd")
        }
    }

    /** 4바이트 Big-Endian 길이와 MP4 파일을 현재 연결로 전송한다. */
    fun sendMp4File(file: File) {
        synchronized(sendLock) {
            val current = synchronized(connectionLock) { connection }
            if (current == null) {
                listener.onError("서버에 연결되어 있지 않아 전송할 수 없습니다.")
                return
            }
            val fileSize = file.length()
            if (fileSize <= 0 || fileSize > Int.MAX_VALUE) {
                listener.onError("전송할 파일 크기가 올바르지 않습니다.")
                return
            }

            val startMs = System.currentTimeMillis()
            try {
                current.output.writeInt(fileSize.toInt())
                val buffer = ByteArray(64 * 1024)
                var bytesSent = 0L
                FileInputStream(file).use { input ->
                    while (true) {
                        val bytesRead = input.read(buffer)
                        if (bytesRead == -1) break
                        current.output.write(buffer, 0, bytesRead)
                        bytesSent += bytesRead
                    }
                }
                if (bytesSent != fileSize) throw java.io.IOException("전송 중 파일 크기가 변경되었습니다.")
                current.output.flush()
                val elapsedMs = System.currentTimeMillis() - startMs
                Log.i(TAG, "MP4 바이너리 스트리밍 완료: $bytesSent 바이트 ($elapsedMs ms 소요)")
                listener.onPayloadSent(bytesSent, elapsedMs)
            } catch (e: Exception) {
                Log.e(TAG, "MP4 전송 실패", e)
                listener.onError("전송 오류: ${e.message}")
                disconnectCurrent(current)
            }
        }
    }

    /** 소켓을 닫아 대기 중인 readLine()을 깨운다. reader.close()를 먼저 호출하면 UI가 멈출 수 있다. */
    fun disconnect() {
        val active: Socket?
        val pending: Socket?
        val job: Job?
        synchronized(connectionLock) {
            ++generation
            active = connection?.socket
            pending = pendingSocket
            job = clientJob
            connection = null
            pendingSocket = null
            clientJob = null
            state = ConnectionState.DISCONNECTED
            listener.onConnectionStateChanged(state, "연결 해제됨")
        }
        closeSocket(active)
        closeSocket(pending)
        job?.cancel()
    }

    private fun disconnectCurrent(current: Connection) {
        closeSocket(current.socket)
        synchronized(connectionLock) {
            if (connection === current) {
                ++generation
                connection = null
                clientJob = null
                state = ConnectionState.DISCONNECTED
                listener.onConnectionStateChanged(state, "전송 중 연결이 끊어졌습니다.")
            }
        }
    }

    private fun closeSocket(target: Socket?) {
        try {
            target?.close()
        } catch (e: Exception) {
            Log.w(TAG, "소켓 정리 중 경고", e)
        }
    }
}
