package com.nightwise.watchwise.faces

import android.content.Context
import android.content.pm.PackageManager
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.wear.watchfacepush.WatchFacePushManager
import androidx.wear.watchfacepush.WatchFacePushManagerFactory
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File

/** The watch face currently in this app's Watch Face Push slot. */
data class InstalledFace(
    val face: WatchFace,
    val accent: Accent,
    val slotId: String,
    val isActive: Boolean,
)

sealed interface PushResult {
    /** The face is installed and showing on the watch. */
    data object Active : PushResult

    /** Installed; activating needs the one-time SET_PUSHED_WATCH_FACE_AS_ACTIVE permission. */
    data class NeedsActivatePermission(val slotId: String) : PushResult

    /** Installed, but the app can't make it active (permission denied / already used). */
    data object InstalledNotActive : PushResult

    /** Watch Face Push isn't available (Wear OS 5 or older). */
    data object Unsupported : PushResult

    data class Failed(val message: String, val retryable: Boolean = false) : PushResult
}

/**
 * Installs and activates our Watch Face Format faces with Watch Face Push.
 *
 * Wear OS 6 gives each app one slot. The first face is added to the slot and made active
 * (Wear OS allows an app to do that once, after a runtime permission). Picking another face
 * or accent later replaces the face in that same slot, which keeps it on screen.
 */
object FacePusher {
    const val ACTIVATE_PERMISSION = "com.google.wear.permission.SET_PUSHED_WATCH_FACE_AS_ACTIVE"
    private const val TAG = "FacePusher"
    private const val ATTEMPTS = 3
    private const val RETRY_DELAY_MS = 1_500L

    /** Bumped whenever the slot may have changed, so open screens reload (also after phone requests). */
    private val _changes = MutableStateFlow(0)
    val changes: StateFlow<Int> = _changes

    /** One slot, so one install at a time (the watch UI and the phone can both ask). */
    private val slotLock = Mutex()

    val isSupported: Boolean get() = WatchFacePushManagerFactory.isSupported()

    private fun manager(context: Context) =
        WatchFacePushManagerFactory.createWatchFacePushManager(context.applicationContext)

    fun hasActivatePermission(context: Context) =
        ContextCompat.checkSelfPermission(context, ACTIVATE_PERMISSION) == PackageManager.PERMISSION_GRANTED

    /** What is in our slot right now, or null (nothing installed / unsupported / error). */
    suspend fun installed(context: Context): InstalledFace? {
        if (!isSupported) return null
        return try {
            val m = manager(context)
            val details = m.listWatchFaces().installedWatchFaceDetails.firstOrNull() ?: return null
            val (face, accent) = WatchFace.fromPackage(details.packageName) ?: return null
            InstalledFace(face, accent, details.slotId, m.isWatchFaceActive(details.packageName))
        } catch (e: Exception) {
            Log.w(TAG, "Could not read installed watch face", e)
            null
        }
    }

    /** Install (or swap in) [face] with [accent], then make it active if possible. */
    suspend fun push(context: Context, face: WatchFace, accent: Accent): PushResult {
        if (!isSupported) return PushResult.Unsupported
        return try {
            slotLock.withLock { pushWithRetry(context, face, accent) }
        } finally {
            _changes.update { it + 1 }
        }
    }

    /**
     * Wear OS sometimes fails an update with an "unknown error" (it tries to show the new face
     * before it has finished registering it) and keeps the old one. Trying again works.
     */
    private suspend fun pushWithRetry(context: Context, face: WatchFace, accent: Accent): PushResult {
        repeat(ATTEMPTS - 1) { attempt ->
            val result = pushOnce(context, face, accent)
            if (result !is PushResult.Failed || !result.retryable) return result
            delay(RETRY_DELAY_MS * (attempt + 1))
        }
        return pushOnce(context, face, accent)
    }

    private suspend fun pushOnce(context: Context, face: WatchFace, accent: Accent): PushResult {
        val m = manager(context)
        val target = face.packageName(accent)
        return try {
            val slot = m.listWatchFaces().installedWatchFaceDetails.firstOrNull()
            val details = when {
                slot == null -> withApk(context, face, accent) { fd, token -> m.addWatchFace(fd, token) }
                slot.packageName == target -> slot
                else -> withApk(context, face, accent) { fd, token -> m.updateWatchFace(slot.slotId, fd, token) }
            }
            when {
                m.isWatchFaceActive(details.packageName) -> PushResult.Active
                !hasActivatePermission(context) -> PushResult.NeedsActivatePermission(details.slotId)
                else -> activate(context, details.slotId)
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.e(TAG, "Push failed for $target", e)
            PushResult.Failed(
                message = e.message ?: e.javaClass.simpleName,
                retryable = e is WatchFacePushManager.UpdateWatchFaceException &&
                    e.errorCode == WatchFacePushManager.UpdateWatchFaceException.ERROR_UNKNOWN,
            )
        }
    }

    /** Make the face in [slotId] the watch's active face. */
    suspend fun activate(context: Context, slotId: String): PushResult = try {
        manager(context).setWatchFaceAsActive(slotId)
        _changes.update { it + 1 }
        PushResult.Active
    } catch (e: WatchFacePushManager.SetWatchFaceAsActiveException) {
        // Allowed only once per app; after that the user picks it from the watch face list.
        Log.w(TAG, "setWatchFaceAsActive refused", e)
        PushResult.InstalledNotActive
    }

    /** Hands the bundled APK (assets/watchfaces/<face>_<accent>.apk) and its token to [block]. */
    private suspend fun <T> withApk(
        context: Context,
        face: WatchFace,
        accent: Accent,
        block: suspend (ParcelFileDescriptor, String) -> T,
    ): T {
        val name = face.assetName(accent)
        val (file, token) = withContext(Dispatchers.IO) {
            val file = File(context.cacheDir, "$name.apk")
            context.assets.open("watchfaces/$name.apk").use { input ->
                file.outputStream().use { input.copyTo(it) }
            }
            val token = context.assets.open("watchfaces/${name}_token.txt").bufferedReader().use { it.readText().trim() }
            file to token
        }
        try {
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
                block(fd, token)
            }
        } finally {
            file.delete()
        }
    }
}
