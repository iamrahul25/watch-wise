package com.nightwise.watchwise.debug

import android.app.Activity
import android.app.Application
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.ContentProvider
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ServiceInfo
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.util.Log
import com.nightwise.watchwise.R
import com.nightwise.watchwise.link.PhoneRequests
import com.nightwise.watchwise.link.WatchLink
import kotlinx.coroutines.runBlocking
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

private const val TAG = "EmulatorBridge"

private val isEmulator get() = Build.HARDWARE == "ranchu" || Build.HARDWARE == "goldfish"

/**
 * Debug builds on an emulator only. Listens on the watch's loopback interface; the host runs
 * `adb -s <watch> forward tcp:8765 tcp:8765` and the phone emulator reaches it at 10.0.2.2:8765.
 *
 * One request per connection: a path line and a JSON line, answered with one JSON line.
 */
class EmulatorBridgeService : Service() {
    private var server: ServerSocket? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val channel = NotificationChannel("bridge", "Emulator bridge", NotificationManager.IMPORTANCE_MIN)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        val notification = Notification.Builder(this, channel.id)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("Emulator bridge (debug)")
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1, notification)
        }
        if (server == null) listen()
        return START_STICKY
    }

    override fun onDestroy() {
        server?.close()
        server = null
    }

    private fun listen() {
        val socket = try {
            ServerSocket(WatchLink.DEBUG_BRIDGE_PORT, 8, InetAddress.getByName("127.0.0.1"))
        } catch (e: Exception) {
            Log.w(TAG, "Could not listen", e)
            return
        }
        server = socket
        thread(name = TAG) {
            while (!socket.isClosed) {
                val client = try {
                    socket.accept()
                } catch (e: Exception) {
                    break
                }
                thread(name = "$TAG-request") { serve(client) }
            }
        }
        Log.i(TAG, "Listening on port ${WatchLink.DEBUG_BRIDGE_PORT}")
    }

    private fun serve(client: Socket) {
        try {
            client.use {
                it.soTimeout = 10_000
                val input = it.getInputStream().bufferedReader()
                val path = input.readLine() ?: return
                val body = input.readLine() ?: return
                val reply = runBlocking { PhoneRequests.handle(applicationContext, path, body.toByteArray()) }
                it.getOutputStream().apply {
                    write(reply)
                    write('\n'.code)
                    flush()
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Request failed", e)
        }
    }
}

/** Starts the bridge the first time the app is on screen (a ContentProvider needs no app code). */
class EmulatorBridgeStarter : ContentProvider() {
    override fun onCreate(): Boolean {
        val app = context?.applicationContext as? Application ?: return true
        if (!isEmulator) return true
        app.registerActivityLifecycleCallbacks(object : Application.ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                activity.startForegroundService(Intent(activity, EmulatorBridgeService::class.java))
            }

            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })
        return true
    }

    override fun query(u: Uri, p: Array<String>?, s: String?, a: Array<String>?, o: String?): Cursor? = null
    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<String>?) = 0
}
