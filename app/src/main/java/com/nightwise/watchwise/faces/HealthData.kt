package com.nightwise.watchwise.faces

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.BatteryManager
import android.os.Build
import android.os.SystemClock
import android.text.format.DateFormat
import androidx.core.content.ContextCompat
import java.time.LocalDate

/**
 * Live data shared by the watch face services and the menu previews (same process).
 *
 * - Battery: the sticky ACTION_BATTERY_CHANGED broadcast (no permission).
 * - Steps today: the hardware step counter (counts since boot) minus a stored
 *   midnight baseline. Needs ACTIVITY_RECOGNITION.
 * - Heart rate: the heart-rate sensor, only switched on while a face is visible
 *   and interactive (never in ambient) to save battery. Needs BODY_SENSORS
 *   (Wear OS 5 and older) or health.READ_HEART_RATE (Wear OS 6+).
 * - Weather: not implemented yet, so temperature is always null.
 */
object HealthData {
    private const val PREFS = "health_data"

    val heartRatePermission: String =
        if (Build.VERSION.SDK_INT >= 36) "android.permission.health.READ_HEART_RATE"
        else Manifest.permission.BODY_SENSORS

    val sensorPermissions: Array<String>
        get() = arrayOf(Manifest.permission.ACTIVITY_RECOGNITION, heartRatePermission)

    @Volatile private var stepsToday: Int? = null
    @Volatile private var heartRate: Int? = null
    @Volatile private var lastHeartRateAt = 0L
    @Volatile private var battery = -1
    @Volatile private var batteryReadAt = 0L

    private var stepListening = false
    private val heartRateOwners = mutableSetOf<Any>()
    private var heartRateListening = false

    fun hasPermission(context: Context, permission: String) =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    fun hasSensorPermissions(context: Context) = sensorPermissions.all { hasPermission(context, it) }

    /** Release builds don't declare the sensor permissions (debug only), so there is nothing to ask for. */
    fun sensorsDeclared(context: Context): Boolean {
        val requested = context.packageManager
            .getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS).requestedPermissions
            ?: return false
        return sensorPermissions.all { it in requested }
    }

    /** Start the step counter if allowed. Safe to call many times. */
    @Synchronized
    fun start(context: Context) {
        val app = context.applicationContext
        if (stepListening || !hasPermission(app, Manifest.permission.ACTIVITY_RECOGNITION)) return
        val sm = app.getSystemService(SensorManager::class.java) ?: return
        val sensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER) ?: return
        loadStoredSteps(app)
        stepListening = sm.registerListener(StepListener(app), sensor, SensorManager.SENSOR_DELAY_NORMAL, 60_000_000)
    }

    /** Turn the heart-rate sensor on while at least one owner (visible face or preview) wants it. */
    @Synchronized
    fun setHeartRateActive(owner: Any, context: Context, active: Boolean) {
        if (active) heartRateOwners.add(owner) else heartRateOwners.remove(owner)
        val app = context.applicationContext
        val sm = app.getSystemService(SensorManager::class.java) ?: return
        val want = heartRateOwners.isNotEmpty() && hasPermission(app, heartRatePermission)
        if (want && !heartRateListening) {
            val sensor = sm.getDefaultSensor(Sensor.TYPE_HEART_RATE) ?: return
            heartRateListening = sm.registerListener(HeartRateListener, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        } else if (!want && heartRateListening) {
            sm.unregisterListener(HeartRateListener)
            heartRateListening = false
        }
    }

    fun snapshot(context: Context): FaceData {
        val now = SystemClock.elapsedRealtime()
        if (battery < 0 || now - batteryReadAt > 30_000) {
            battery = readBattery(context)
            batteryReadAt = now
        }
        // A heart-rate reading older than 10 minutes is no longer meaningful.
        val hr = heartRate?.takeIf { now - lastHeartRateAt < 10 * 60_000 }
        return FaceData(
            battery = battery.coerceIn(0, 100),
            steps = stepsToday,
            heartRate = hr,
            temperatureC = null,
            is24Hour = DateFormat.is24HourFormat(context),
        )
    }

    private fun readBattery(context: Context): Int {
        val intent: Intent? = context.applicationContext
            .registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        return if (level < 0 || scale <= 0) 0 else level * 100 / scale
    }

    private fun loadStoredSteps(context: Context) {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (p.getString("date", null) == LocalDate.now().toString()) {
            stepsToday = p.getInt("today", 0)
        }
    }

    private class StepListener(private val context: Context) : SensorEventListener {
        override fun onSensorChanged(event: SensorEvent) {
            val counter = event.values[0].toLong()
            val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val today = LocalDate.now().toString()
            val last = p.getLong("last", -1)
            var base = p.getLong("base", counter)
            var steps = p.getInt("today", 0)
            when {
                // New day: count from the last value seen yesterday (or now, if none).
                p.getString("date", null) != today -> base = if (last in 0..counter) last else counter
                // Counter went backwards: the watch rebooted. Keep today's steps.
                counter < last -> base = counter - steps
            }
            steps = (counter - base).coerceAtLeast(0).toInt()
            stepsToday = steps
            p.edit().putString("date", today).putLong("base", base).putLong("last", counter)
                .putInt("today", steps).apply()
        }

        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
    }

    private object HeartRateListener : SensorEventListener {
        override fun onSensorChanged(event: SensorEvent) {
            val bpm = event.values.firstOrNull()?.toInt() ?: return
            if (bpm > 0) {
                heartRate = bpm
                lastHeartRateAt = SystemClock.elapsedRealtime()
            }
        }

        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
    }
}
