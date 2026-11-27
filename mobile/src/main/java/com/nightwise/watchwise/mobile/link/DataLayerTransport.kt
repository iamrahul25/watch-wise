package com.nightwise.watchwise.mobile.link

import android.content.Context
import android.content.Intent
import androidx.concurrent.futures.await
import androidx.core.net.toUri
import androidx.wear.remote.interactions.RemoteActivityHelper
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.Node
import com.google.android.gms.wearable.Wearable
import com.nightwise.watchwise.link.FaceRequest
import com.nightwise.watchwise.link.WatchLink
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONObject

/** A paired watch, over Google Play services' Wearable Data Layer. */
class DataLayerTransport(context: Context) : WatchTransport {
    private val context = context.applicationContext
    private val capabilities = Wearable.getCapabilityClient(this.context)
    private val messages = Wearable.getMessageClient(this.context)
    private val nodes = Wearable.getNodeClient(this.context)

    override suspend fun request(path: String, body: JSONObject): JSONObject = guarded {
        val watch = watchWithApp()
        // Installing a face takes a few seconds; reading the state should be quick.
        val timeout = if (path == WatchLink.PATH_STATE) 8_000L else 45_000L
        val reply = withTimeout(timeout) {
            messages.sendRequest(watch.id, path, body.toString().toByteArray()).await()
        }
        JSONObject(String(reply))
    }

    override suspend fun openOnWatch(face: FaceRequest) = guarded {
        startOnWatch(watchWithApp().id, WatchLink.faceUri(face))
    }

    /** Opens Watch Wise's Play Store page on a watch that doesn't have it yet. */
    suspend fun openStoreOnWatch(nodeId: String) = guarded {
        startOnWatch(nodeId, "market://details?id=${context.packageName}")
    }

    private suspend fun startOnWatch(nodeId: String, uri: String) {
        val intent = Intent(Intent.ACTION_VIEW, uri.toUri()).addCategory(Intent.CATEGORY_BROWSABLE)
        RemoteActivityHelper(context).startRemoteActivity(intent, nodeId).await()
    }

    private suspend fun watchWithApp(): Node {
        val withApp = capabilities
            .getCapability(WatchLink.WATCH_CAPABILITY, CapabilityClient.FILTER_REACHABLE)
            .await().nodes
        withApp.firstOrNull { it.isNearby }?.let { return it }
        withApp.firstOrNull()?.let { return it }
        val any = nodes.connectedNodes.await().firstOrNull()
            ?: throw WatchUnreachableException("No watch is connected")
        throw AppMissingException(any.id, any.displayName)
    }

    /** Turns Play services failures (no Wear support, timeouts, lost link) into "unreachable". */
    private suspend fun <T> guarded(block: suspend () -> T): T = try {
        block()
    } catch (e: WatchUnreachableException) {
        throw e
    } catch (e: TimeoutCancellationException) {
        throw WatchUnreachableException("The watch didn't answer", e)
    } catch (e: ApiException) {
        throw WatchUnreachableException("No watch is connected", e)
    } catch (e: RemoteActivityHelper.RemoteIntentException) {
        throw WatchUnreachableException("The watch couldn't open that", e)
    }
}
