package com.strikezone.mobile.network

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketTimeoutException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class TcpDumpClientTest {
    private lateinit var server: ServerSocket
    private lateinit var client: TcpDumpClient
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val connected = CountDownLatch(1)
    private val disconnected = CountDownLatch(1)

    @Before
    fun setUp() {
        server = ServerSocket(0, 2, InetAddress.getLoopbackAddress())
        client = TcpDumpClient(object : TcpEventListener {
            override fun onConnectionStateChanged(state: ConnectionState, message: String?) {
                if (state == ConnectionState.CONNECTED) connected.countDown()
                if (state == ConnectionState.DISCONNECTED) disconnected.countDown()
            }

            override fun onDumpRequested(durationSeconds: Float) = Unit
            override fun onPayloadSent(bytesSent: Long, elapsedMs: Long) = Unit
            override fun onError(errorMessage: String) = Unit
        })
    }

    @After
    fun tearDown() {
        client.disconnect()
        server.close()
        scope.cancel()
    }

    @Test
    fun disconnectReturnsWhileServerIsSilent() {
        client.connect("127.0.0.1", server.localPort, scope)
        server.accept().use {
            assertTrue(connected.await(2, TimeUnit.SECONDS))
            val stopper = Thread { client.disconnect() }.apply { isDaemon = true; start() }
            stopper.join(2000)
            assertFalse("수신 대기 중 연결 해제가 멈추면 안 됩니다.", stopper.isAlive)
            assertEquals(ConnectionState.DISCONNECTED, client.state)
        }
    }

    @Test
    fun serverEofChangesStateToDisconnected() {
        client.connect("127.0.0.1", server.localPort, scope)
        val accepted = server.accept()
        assertTrue(connected.await(2, TimeUnit.SECONDS))
        accepted.close()
        assertTrue("서버 종료 시 연결 해제 상태를 알려야 합니다.", disconnected.await(2, TimeUnit.SECONDS))
        assertEquals(ConnectionState.DISCONNECTED, client.state)
    }

    @Test
    fun repeatedConnectDoesNotOpenSecondSocket() {
        val acceptedCount = AtomicInteger(0)
        val acceptor = Thread {
            try {
                server.soTimeout = 800
                server.accept().use { first ->
                    acceptedCount.incrementAndGet()
                    try {
                        server.accept().use { second -> acceptedCount.incrementAndGet() }
                    } catch (_: SocketTimeoutException) {
                        // 두 번째 연결이 없으면 예상대로 타임아웃한다.
                    }
                }
            } catch (_: SocketTimeoutException) {
                // 연결 실패는 아래의 connected 검증에서 확인한다.
            }
        }.apply { isDaemon = true; start() }

        client.connect("127.0.0.1", server.localPort, scope)
        client.connect("127.0.0.1", server.localPort, scope)
        assertTrue(connected.await(2, TimeUnit.SECONDS))
        acceptor.join(2000)
        assertEquals(1, acceptedCount.get())
    }

    @Test
    fun oldReceiveLoopCannotDisconnectNewConnection() {
        client.connect("127.0.0.1", server.localPort, scope)
        val first = server.accept()
        assertTrue(connected.await(2, TimeUnit.SECONDS))

        client.disconnect()
        client.connect("127.0.0.1", server.localPort, scope)
        val second = server.accept()
        try {
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2)
            while (client.state != ConnectionState.CONNECTED && System.nanoTime() < deadline) {
                Thread.sleep(10)
            }
            assertEquals(ConnectionState.CONNECTED, client.state)
            Thread.sleep(100)
            assertEquals("이전 수신 루프가 새 연결을 종료하면 안 됩니다.", ConnectionState.CONNECTED, client.state)
        } finally {
            first.close()
            second.close()
        }
    }
}
