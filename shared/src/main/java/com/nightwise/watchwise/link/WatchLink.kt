package com.nightwise.watchwise.link

import org.json.JSONObject

/**
 * The phone <-> watch protocol: the phone sends a request (path + JSON), the watch answers
 * with JSON. Carried by the Wearable Data Layer (MessageClient.sendRequest). Debug builds
 * can also carry it over a loopback socket between two emulators ([DEBUG_BRIDGE_PORT]).
 */
object WatchLink {
    /** Capability the watch app declares (app/src/main/res/values/wear.xml). */
    const val WATCH_CAPABILITY = "watchwise_watch"

    const val PATH_PREFIX = "/watchwise"

    /** -> {} <- [WatchState] */
    const val PATH_STATE = "$PATH_PREFIX/state"

    /** -> [FaceRequest] <- [SetReply] */
    const val PATH_SET_FACE = "$PATH_PREFIX/set"

    /** -> [FaceRequest] <- [SetReply] : show that face in the watch app (to allow a permission there). */
    const val PATH_OPEN = "$PATH_PREFIX/open"

    /** Deep link into the watch app: watchwise://face/<faceId>?accent=<name> */
    fun faceUri(request: FaceRequest) = "watchwise://face/${request.faceId}?accent=${request.accent}"

    const val DEBUG_BRIDGE_PORT = 8765
}

data class FaceRequest(val faceId: String, val accent: String) {
    fun toJson(): JSONObject = JSONObject().put("face", faceId).put("accent", accent)

    companion object {
        fun fromJson(json: JSONObject) = FaceRequest(json.getString("face"), json.getString("accent"))
    }
}

/** The face in the watch's Watch Face Push slot. [active] = it is what the watch shows. */
data class RemoteFace(val faceId: String, val accent: String, val active: Boolean)

data class WatchState(
    val deviceName: String,
    /** Wear OS API level. */
    val sdk: Int,
    /** Watch Face Push available (Wear OS 6+). */
    val pushSupported: Boolean,
    /** The one-time "set as active" permission is granted. */
    val canActivate: Boolean,
    val installed: RemoteFace?,
    val battery: Int,
    val steps: Int?,
    val heartRate: Int?,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("device", deviceName)
        .put("sdk", sdk)
        .put("pushSupported", pushSupported)
        .put("canActivate", canActivate)
        .put("battery", battery)
        .putOpt("steps", steps)
        .putOpt("heartRate", heartRate)
        .putOpt(
            "installed",
            installed?.let { JSONObject().put("face", it.faceId).put("accent", it.accent).put("active", it.active) },
        )

    companion object {
        fun fromJson(json: JSONObject) = WatchState(
            deviceName = json.getString("device"),
            sdk = json.getInt("sdk"),
            pushSupported = json.getBoolean("pushSupported"),
            canActivate = json.getBoolean("canActivate"),
            installed = json.optJSONObject("installed")?.let {
                RemoteFace(it.getString("face"), it.getString("accent"), it.getBoolean("active"))
            },
            battery = json.getInt("battery"),
            steps = json.optIntOrNull("steps"),
            heartRate = json.optIntOrNull("heartRate"),
        )

        private fun JSONObject.optIntOrNull(key: String) = if (has(key)) getInt(key) else null
    }
}

enum class SetStatus {
    /** Installed and showing on the watch. */
    ACTIVE,

    /** Installed; the user has to allow activation once, on the watch. */
    NEEDS_PERMISSION,

    /** Installed, but the user has to pick it from the watch face list. */
    NOT_ACTIVE,

    /** Wear OS 5 or older. */
    UNSUPPORTED,

    FAILED,
}

data class SetReply(val status: SetStatus, val message: String? = null) {
    fun toJson(): JSONObject = JSONObject().put("status", status.name).putOpt("message", message)

    companion object {
        fun fromJson(json: JSONObject) = SetReply(
            status = SetStatus.entries.firstOrNull { it.name == json.optString("status") } ?: SetStatus.FAILED,
            message = if (json.has("message")) json.getString("message") else null,
        )
    }
}
