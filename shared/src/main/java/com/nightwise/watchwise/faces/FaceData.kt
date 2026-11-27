package com.nightwise.watchwise.faces

/** Everything a face needs besides the time. `null` means "not available" and is drawn as "--". */
data class FaceData(
    val battery: Int,
    val steps: Int?,
    val heartRate: Int?,
    val temperatureC: Int?,
    val is24Hour: Boolean,
) {
    /** Rough estimate: ~0.04 kcal per step for an average adult. */
    val calories: Int? get() = steps?.let { (it * 0.04).toInt() }
}
