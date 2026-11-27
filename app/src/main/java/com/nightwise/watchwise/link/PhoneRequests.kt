package com.nightwise.watchwise.link

import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.core.net.toUri
import com.nightwise.watchwise.MainActivity
import com.nightwise.watchwise.faces.FacePrefs
import com.nightwise.watchwise.faces.FacePusher
import com.nightwise.watchwise.faces.HealthData
import com.nightwise.watchwise.faces.PushResult
import com.nightwise.watchwise.faces.WatchFace
import org.json.JSONObject

/** Answers the phone companion's requests (see [WatchLink]), whichever way they arrived. */
object PhoneRequests {
    private const val TAG = "PhoneRequests"

    suspend fun handle(context: Context, path: String, body: ByteArray): ByteArray {
        val app = context.applicationContext
        val reply = try {
            val json = if (body.isEmpty()) JSONObject() else JSONObject(String(body))
            when (path) {
                WatchLink.PATH_STATE -> state(app).toJson()
                WatchLink.PATH_SET_FACE -> setFace(app, FaceRequest.fromJson(json)).toJson()
                WatchLink.PATH_OPEN -> open(app, FaceRequest.fromJson(json)).toJson()
                else -> SetReply(SetStatus.FAILED, "Unknown request. Update the watch app.").toJson()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Request $path failed", e)
            SetReply(SetStatus.FAILED, e.message ?: e.javaClass.simpleName).toJson()
        }
        return reply.toString().toByteArray()
    }

    private suspend fun state(context: Context): WatchState {
        HealthData.start(context)
        val data = HealthData.snapshot(context)
        val installed = FacePusher.installed(context)
        return WatchState(
            deviceName = Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME)
                ?: Build.MODEL,
            sdk = Build.VERSION.SDK_INT,
            pushSupported = FacePusher.isSupported,
            canActivate = FacePusher.isSupported && FacePusher.hasActivatePermission(context),
            installed = installed?.let { RemoteFace(it.face.id, it.accent.name, it.isActive) },
            battery = data.battery,
            steps = data.steps,
            heartRate = data.heartRate,
        )
    }

    private suspend fun setFace(context: Context, request: FaceRequest): SetReply {
        val face = WatchFace.byId(request.faceId)
            ?: return SetReply(SetStatus.FAILED, "This face isn't in the watch app yet. Update it.")
        val accent = face.accents.firstOrNull { it.name == request.accent }
            ?: return SetReply(SetStatus.FAILED, "Unknown accent colour.")
        FacePrefs.setAccent(context, face, accent.color)
        return when (val result = FacePusher.push(context, face, accent)) {
            PushResult.Active -> SetReply(SetStatus.ACTIVE)
            is PushResult.NeedsActivatePermission -> SetReply(SetStatus.NEEDS_PERMISSION)
            PushResult.InstalledNotActive -> SetReply(SetStatus.NOT_ACTIVE)
            PushResult.Unsupported -> SetReply(SetStatus.UNSUPPORTED)
            is PushResult.Failed -> SetReply(SetStatus.FAILED, result.message)
        }
    }

    /**
     * Used by the debug bridge only: over the Data Layer the phone opens the deep link itself
     * (RemoteActivityHelper). Android only lets this succeed while the app may start activities.
     */
    private fun open(context: Context, request: FaceRequest): SetReply {
        context.startActivity(
            Intent(Intent.ACTION_VIEW, WatchLink.faceUri(request).toUri(), context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
        return SetReply(SetStatus.NEEDS_PERMISSION)
    }
}
