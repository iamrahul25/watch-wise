package com.nightwise.watchwise.mobile.link

import android.os.Build
import com.nightwise.watchwise.link.FaceRequest
import com.nightwise.watchwise.link.WatchLink
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket

/** Debug builds: a phone emulator can also reach a watch emulator without pairing. */
fun emulatorTransport(): WatchTransport? =
    if (Build.HARDWARE == "ranchu" || Build.HARDWARE == "goldfish") EmulatorBridgeTransport() else null

/**
 * Talks to the watch app's debug bridge through the host computer:
 *
 *   adb -s <phone> reverse tcp:8765 tcp:8765   (phone's localhost -> computer)
 *   adb -s <watch> forward tcp:8765 tcp:8765   (computer -> watch)
 *
 * The phone's own localhost, because Android 17 asks for a local network permission before
 * an app may reach the host directly (10.0.2.2). app.py sets up both.
 */
private class EmulatorBridgeTransport : WatchTransport {
    override val isEmulatorBridge = true

    override suspend fun request(path: String, body: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress("127.0.0.1", WatchLink.DEBUG_BRIDGE_PORT), 2_000)
                socket.soTimeout = if (path == WatchLink.PATH_STATE) 8_000 else 45_000
                socket.getOutputStream().apply {
                    write("$path\n$body\n".toByteArray())
                    flush()
                }
                val reply = socket.getInputStream().bufferedReader().readLine()
                    ?: throw WatchUnreachableException("Open Watch Wise on the watch emulator")
                JSONObject(reply)
            }
        } catch (e: IOException) {
            throw WatchUnreachableException("Open Watch Wise on the watch emulator", e)
        }
    }

    override suspend fun openOnWatch(face: FaceRequest) {
        request(WatchLink.PATH_OPEN, face.toJson())
    }
}
