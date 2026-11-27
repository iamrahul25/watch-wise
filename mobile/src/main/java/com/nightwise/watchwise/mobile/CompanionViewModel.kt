package com.nightwise.watchwise.mobile

import android.app.Application
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nightwise.watchwise.faces.Accent
import com.nightwise.watchwise.faces.FacePrefs
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.link.FaceRequest
import com.nightwise.watchwise.link.SetReply
import com.nightwise.watchwise.link.SetStatus
import com.nightwise.watchwise.link.WatchLink
import com.nightwise.watchwise.link.WatchState
import com.nightwise.watchwise.mobile.link.AppMissingException
import com.nightwise.watchwise.mobile.link.DataLayerTransport
import com.nightwise.watchwise.mobile.link.WatchTransport
import com.nightwise.watchwise.mobile.link.emulatorTransport
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** What the phone currently knows about the watch. */
sealed interface Link {
    data object Searching : Link
    data class Connected(val watch: WatchState, val viaEmulator: Boolean) : Link
    data class AppMissing(val nodeId: String, val watchName: String) : Link
    data class Offline(val reason: String) : Link
}

enum class Tone { SUCCESS, ATTENTION, ERROR }

/** The outcome of the last "Set on watch". */
data class Notice(val faceId: String, val tone: Tone, val text: String)

class CompanionViewModel(app: Application) : AndroidViewModel(app) {
    private val dataLayer = DataLayerTransport(app)
    private val transports: List<WatchTransport> = listOfNotNull(dataLayer, emulatorTransport())

    /** The transport that answered last. */
    private var current: WatchTransport? = null
    private val refreshLock = Mutex()
    private var misses = 0

    var link by mutableStateOf<Link>(Link.Searching)
        private set

    /** The face being sent to the watch, if any. */
    var sending by mutableStateOf<FaceRequest?>(null)
        private set

    var notice by mutableStateOf<Notice?>(null)
        private set

    private val accents = mutableStateMapOf<WatchFace, Int>().apply {
        WatchFace.entries.forEach { put(it, FacePrefs.accent(app, it)) }
    }

    fun accent(face: WatchFace): Accent = face.accentFor(accents.getValue(face))

    fun selectAccent(face: WatchFace, accent: Accent) {
        accents[face] = accent.color
        FacePrefs.setAccent(getApplication(), face, accent.color)
        notice = null
    }

    /** Keeps the watch status fresh; run while the app is on screen. */
    suspend fun watchStatus() {
        while (true) {
            if (sending == null) refresh()
            delay(if (link is Link.Connected) 4_000 else 3_000)
        }
    }

    fun retry() {
        link = Link.Searching
        viewModelScope.launch { refresh() }
    }

    private suspend fun refresh() = refreshLock.withLock {
        var appMissing: AppMissingException? = null
        var reason = NO_WATCH
        // The one that worked last goes first.
        for (transport in transports.sortedByDescending { it === current }) {
            try {
                val watch = WatchState.fromJson(transport.request(WatchLink.PATH_STATE))
                if (current == null) adoptAccent(watch)
                current = transport
                misses = 0
                link = Link.Connected(watch, transport.isEmulatorBridge)
                return@withLock
            } catch (e: CancellationException) {
                throw e
            } catch (e: AppMissingException) {
                appMissing = e
            } catch (e: Exception) {
                Log.d(TAG, "No answer from ${transport.javaClass.simpleName}: ${e.message}")
                reason = e.message ?: reason
            }
        }
        // One missed poll isn't a disconnect.
        if (link is Link.Connected && ++misses < 2) return@withLock
        current = null
        link = appMissing?.let { Link.AppMissing(it.nodeId, it.watchName) } ?: Link.Offline(reason)
    }

    /** On (re)connect, show the watch's face in the colour it actually has. */
    private fun adoptAccent(watch: WatchState) {
        val installed = watch.installed ?: return
        val face = WatchFace.byId(installed.faceId) ?: return
        face.accents.firstOrNull { it.name == installed.accent }?.let { selectAccent(face, it) }
    }

    fun setOnWatch(face: WatchFace) {
        if (sending != null) return
        val request = FaceRequest(face.id, accent(face).name)
        sending = request
        notice = null
        viewModelScope.launch {
            try {
                val transport = current ?: run {
                    refresh()
                    current ?: error("No watch is connected")
                }
                val reply = SetReply.fromJson(transport.request(WatchLink.PATH_SET_FACE, request.toJson()))
                if (reply.status == SetStatus.NEEDS_PERMISSION) {
                    // Best effort: the user can also open the app on the watch themselves.
                    runCatching { transport.openOnWatch(request) }
                }
                notice = describe(face, reply)
                refresh()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "Could not set ${face.id}", e)
                notice = Notice(face.id, Tone.ERROR, e.message ?: "Couldn't reach the watch")
            } finally {
                sending = null
            }
        }
    }

    fun installOnWatch(nodeId: String) {
        viewModelScope.launch {
            runCatching { dataLayer.openStoreOnWatch(nodeId) }
                .onFailure { Log.w(TAG, "Could not open the Play Store on the watch", it) }
        }
    }

    private fun describe(face: WatchFace, reply: SetReply): Notice {
        val (tone, text) = when (reply.status) {
            SetStatus.ACTIVE -> Tone.SUCCESS to "${face.title} is now on your watch"
            SetStatus.NEEDS_PERMISSION ->
                Tone.ATTENTION to "One-time step: on your watch, open ${face.title}, tap Set face and choose Allow."
            SetStatus.NOT_ACTIVE ->
                Tone.ATTENTION to "Installed. Long-press your watch face and pick ${face.title}."
            SetStatus.UNSUPPORTED ->
                Tone.ERROR to "Setting faces from the app needs Wear OS 6 or newer."
            SetStatus.FAILED -> Tone.ERROR to "The watch couldn't set the face. ${reply.message.orEmpty()}".trim()
        }
        return Notice(face.id, tone, text)
    }

    private companion object {
        const val TAG = "Companion"
        const val NO_WATCH = "Check Bluetooth and keep your watch nearby"
    }
}
