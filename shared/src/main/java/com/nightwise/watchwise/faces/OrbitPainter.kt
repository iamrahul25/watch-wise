package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.Rect
import android.graphics.Typeface
import java.time.ZonedDateTime

/**
 * Orbit — rings of hours, minutes and seconds turning clockwise so the current time lines up in a
 * pill at 3 o'clock, around the date. The accent colours the pill, seconds and month.
 *
 * Ambient: only the date and the pill with hours and minutes stay lit.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (orbit), which also
 * writes the ring pictures to assets/orbit.
 */
class OrbitPainter(private val assets: AssetManager) : FacePainter {

    private val bold = Fonts.get(assets, Fonts.SPACE_GROTESK, 700)
    private val medium = Fonts.get(assets, Fonts.SPACE_GROTESK, 500)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val image = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val images = HashMap<String, Bitmap>()

    override fun draw(
        canvas: Canvas,
        bounds: Rect,
        time: ZonedDateTime,
        data: FaceData,
        accent: Int,
        ambient: Boolean,
    ) {
        val s = bounds.width() / DESIGN_SIZE
        canvas.drawColor(Color.BLACK)
        canvas.save()
        canvas.translate(bounds.left.toFloat(), bounds.top.toFloat())
        canvas.scale(s, s)

        val hour = time.displayHour(data.is24Hour)
        val seconds = time.second + time.nano / 1e9f
        if (!ambient) {
            picture(canvas, "dial")
            if (data.is24Hour) {
                picture(canvas, "ring_hours24", hour * 15f)
            } else {
                picture(canvas, "ring_hours12", (hour % 12) * 30f)
            }
            picture(canvas, "ring_minutes", time.minute * 6f)
            picture(canvas, "ring_seconds", seconds * 6f)
            picture(canvas, "pill_fill", tint = accent)
        }

        val dateAlpha = if (ambient) 170 else 255
        words(canvas, time.dayShort(), CENTRE, 194f, 11f, medium, GREY, dateAlpha, 0.2f)
        words(canvas, "${time.dayOfMonth}", CENTRE, 224.5f, 48.5f, bold, Color.WHITE, dateAlpha)
        words(canvas, time.monthShort(), CENTRE, 256f, 10.5f, bold, accent, dateAlpha, 0.2f)

        val timeAlpha = if (ambient) 200 else 255
        words(canvas, "$hour", CENTRE + HOUR_R, CENTRE, 23.5f, bold, Color.WHITE, timeAlpha)
        words(canvas, time.minute.pad2(), CENTRE + MINUTE_R, CENTRE, 14f, bold, Color.WHITE, timeAlpha)
        if (!ambient) {
            for (offset in intArrayOf(-1, 1)) {
                val minute = ((time.minute + offset + 60) % 60).pad2()
                // Clockwise: the next minute sits above the current one.
                turned(canvas, -offset * 6f) {
                    words(canvas, minute, CENTRE + MINUTE_R, CENTRE, 14f, bold, Color.WHITE, 255)
                }
            }
            // This second leaves downwards as the next arrives from above, fading at the edge.
            val part = seconds - time.second
            for (next in 0..1) {
                val alpha = (if (next == 0) (0.9f - part) * 850 else (part - 0.1f) * 850).toInt().coerceIn(0, 255)
                turned(canvas, (part - next) * 6f) {
                    words(canvas, ((time.second + next) % 60).pad2(), CENTRE + SECOND_R, CENTRE, 12f, bold, accent, alpha)
                }
            }
        }
        // Over the numbers, so the pill's edge clips the ones leaving it.
        picture(canvas, "pill_line", tint = accent, alpha = if (ambient) 140 else 255)
        canvas.restore()
    }

    /** Runs [drawing] turned [angle] degrees clockwise about the centre of the face. */
    private inline fun turned(canvas: Canvas, angle: Float, drawing: () -> Unit) {
        canvas.save()
        canvas.rotate(angle, CENTRE, CENTRE)
        drawing()
        canvas.restore()
    }

    /** Draws assets/orbit/[name].png over the whole face, turned [angle] degrees clockwise. */
    private fun picture(canvas: Canvas, name: String, angle: Float = 0f, tint: Int? = null, alpha: Int = 255) {
        val bitmap = images.getOrPut(name) { assets.open("orbit/$name.png").use { BitmapFactory.decodeStream(it) } }
        image.colorFilter = tint?.let { PorterDuffColorFilter(it, PorterDuff.Mode.SRC_IN) }
        image.alpha = alpha
        canvas.save()
        canvas.rotate(angle, CENTRE, CENTRE)
        canvas.drawBitmap(bitmap, 0f, 0f, image)
        canvas.restore()
    }

    /** Text centred on ([x], [y]), measured on the digit height. */
    private fun words(
        canvas: Canvas,
        value: String,
        x: Float,
        y: Float,
        size: Float,
        font: Typeface,
        color: Int,
        alpha: Int,
        spacing: Float = 0f,
    ) {
        text.typeface = font
        text.textSize = size
        text.letterSpacing = spacing
        text.color = color
        text.alpha = alpha
        canvas.drawText(value, x, y + 0.35f * size, text)
    }

    private companion object {
        const val CENTRE = 225f
        const val HOUR_R = 100.7f
        const val MINUTE_R = 152.2f
        const val SECOND_R = 200.5f
        const val GREY = 0xFF8A8A8A.toInt()
    }
}
