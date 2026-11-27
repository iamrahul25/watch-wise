package com.nightwise.watchwise.mobile.link

import com.nightwise.watchwise.link.FaceRequest
import org.json.JSONObject

/** One way of reaching the watch. */
interface WatchTransport {
    /** Sends one request. Throws [WatchUnreachableException] if there is no watch this way. */
    suspend fun request(path: String, body: JSONObject = JSONObject()): JSONObject

    /** Brings up [face] in the watch app. */
    suspend fun openOnWatch(face: FaceRequest)

    /** True when this is the debug-only emulator link. */
    val isEmulatorBridge: Boolean get() = false
}

open class WatchUnreachableException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** A watch is connected, but Watch Wise isn't installed on it. */
class AppMissingException(val nodeId: String, val watchName: String) :
    WatchUnreachableException("Watch Wise isn't installed on $watchName")
