package com.nightwise.watchwise.link

import com.google.android.gms.tasks.Task
import com.google.android.gms.tasks.TaskCompletionSource
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/** Receives the phone companion's requests over the Wearable Data Layer. */
class PhoneRequestService : WearableListenerService() {

    override fun onRequest(nodeId: String, path: String, request: ByteArray): Task<ByteArray> {
        val reply = TaskCompletionSource<ByteArray>()
        // Not tied to the service: installing a face may outlive this callback.
        scope.launch {
            reply.setResult(PhoneRequests.handle(applicationContext, path, request))
        }
        return reply.task
    }

    private companion object {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    }
}
