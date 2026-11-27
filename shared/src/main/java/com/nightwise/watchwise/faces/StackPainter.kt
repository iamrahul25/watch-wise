package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Typeface
import androidx.core.graphics.PathParser
import java.time.ZonedDateTime
import java.time.format.TextStyle
import java.util.Locale

/**
 * Stack — condensed hours over accent minutes, a column of date and stats, a seconds ring,
 * sunrise / sunset on top and a notification pill at the bottom.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (stack), which is laid
 * out on the design's 480 x 480 artboard. Sunrise, weather condition, the next event and
 * the unread count come from the watch itself, so the preview shows placeholders for them.
 *
 * Ambient: thin grey digits and a dimmed date only.
 */
class StackPainter(assets: AssetManager) : FacePainter {

    private val light = Fonts.get(assets, Fonts.SPACE_GROTESK, 300)
    private val medium = Fonts.get(assets, Fonts.SPACE_GROTESK, 500)
    private val semiBold = Fonts.get(assets, Fonts.SPACE_GROTESK, 600)
    private val bold = Fonts.get(assets, Fonts.SPACE_GROTESK, 700)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val sun = icon(
        "M17 12a5 5 0 1 1-10 0a5 5 0 1 1 10 0z" +
            "M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5",
    )
    private val heart = icon(
        "M12 20s-7-4.4-9.2-8.7A5.2 5.2 0 0 1 12 6.4a5.2 5.2 0 0 1 9.2 4.9C19 15.6 12 20 12 20z",
    )
    private val footsteps = icon(
        "M5 16c0-3 .8-7 2.8-7S10 12 10 14s-1 4-2.5 4S5 17 5 16z" +
            "M14 10c0-3 .8-7 2.8-7S19 6 19 8s-1 4-2.5 4S14 11 14 10z",
    )
    private val batteryIcon = icon(
        "M4 7H17C18.1 7 19 7.9 19 9V15C19 16.1 18.1 17 17 17H4C2.9 17 2 16.1 2 15V9C2 7.9 2.9 7 4 7Z" +
            "M22 11v2M5 10v4M8 10v4M11 10v4",
    )
    private val bell = icon("M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0")

    override fun draw(
        canvas: Canvas,
        bounds: Rect,
        time: ZonedDateTime,
        data: FaceData,
        accent: Int,
        ambient: Boolean,
    ) {
        val s = bounds.width() / ARTBOARD
        canvas.drawColor(Color.BLACK)
        canvas.save()
        canvas.translate(bounds.left.toFloat(), bounds.top.toFloat())
        canvas.scale(s, s)

        val face = if (ambient) light else bold
        digits(canvas, time.displayHour(data.is24Hour).pad2(), HOURS_BASELINE, face,
            if (ambient) AMBIENT_HOURS else WHITE)
        digits(canvas, time.minute.pad2(), MINUTES_BASELINE, face, if (ambient) AMBIENT_MINUTES else accent)

        // Date block.
        val dateAlpha = if (ambient) 160 else 255
        val day = time.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.US).uppercase(Locale.US)
        val month = time.month.getDisplayName(TextStyle.SHORT, Locale.US)
        label(canvas, day, COLUMN, 112f, 15f, semiBold, 12f, GREY, dateAlpha, spacing = 3f)
        label(canvas, "${time.dayOfMonth} $month", COLUMN, 127f, 27f, bold, 22f, WHITE, dateAlpha)

        if (!ambient) {
            ring(canvas, time.second, accent)
            drawIcon(canvas, sun, 190f, 62.5f, 16f, SUN)
            label(canvas, "--:--", 214f, 53f, 19f, medium, 13f, GREY, spacing = 1.5f)
            stats(canvas, data, accent)
            pill(canvas, accent)
        }
        canvas.restore()
    }

    private fun stats(canvas: Canvas, data: FaceData, accent: Int) {
        text.color = DIVIDER
        canvas.drawRect(COLUMN, 167f, COLUMN + 100, 168f, text)

        val x = COLUMN + 28
        drawIcon(canvas, sun, COLUMN, 199f, 20f, SUN)
        label(canvas, data.temperatureC?.let { "$it°" } ?: "--°", x, 182f, 21f, bold, 18f, WHITE)
        label(canvas, "No weather", x, 203f, 13f, medium, 11f, GREY)

        drawIcon(canvas, heart, COLUMN, 240.5f, 20f, HEART)
        val bpm = data.heartRate?.toString() ?: "--"
        label(canvas, bpm, x, 229.5f, 22f, bold, 18f, WHITE)
        val bpmWidth = text.measureText(bpm)
        label(canvas, "BPM", x + bpmWidth + 5, 235f, 14f, medium, 11f, GREY)

        drawIcon(canvas, footsteps, COLUMN, 276.5f, 20f, accent)
        val steps = data.steps?.let { "%,d".format(Locale.US, it) } ?: "--"
        label(canvas, steps, x, 265.5f, 22f, bold, 18f, WHITE)

        drawIcon(canvas, batteryIcon, COLUMN, 312f, 20f, BATTERY)
        label(canvas, "${data.battery}%", x, 301f, 22f, bold, 18f, WHITE)
    }

    private fun pill(canvas: Canvas, accent: Int) {
        line.color = PILL
        line.strokeWidth = 1f
        canvas.drawRoundRect(138f, 396f, 342f, 424f, 14f, 14f, line)
        drawIcon(canvas, bell, 151f, 410f, 14f, accent)
        label(canvas, "0", 180f, 402f, 16f, medium, 12f, accent, centred = true)
        text.color = GREY
        canvas.drawCircle(197f, 410f, 1.25f, text)
        label(canvas, "No events", 204f, 402f, 16f, medium, 12f, WHITE)
    }

    /** Two condensed digits, each centred in a fixed-width cell. */
    private fun digits(canvas: Canvas, value: String, baseline: Float, face: Typeface, color: Int) {
        text.typeface = face
        text.textSize = TIME_SIZE
        text.textScaleX = DIGIT_SCALE
        text.letterSpacing = 0f
        text.textAlign = Paint.Align.CENTER
        text.color = color
        val cell = DIGIT_ADVANCE * TIME_SIZE
        value.forEachIndexed { i, c ->
            canvas.drawText(c.toString(), TIME_CENTRE + (i - 0.5f) * cell, baseline, text)
        }
        text.textScaleX = 1f
    }

    /** Text in a CSS line box starting at [top]; [x] is its left edge, or centre if [centred]. */
    private fun label(
        canvas: Canvas,
        value: String,
        x: Float,
        top: Float,
        box: Float,
        face: Typeface,
        size: Float,
        color: Int,
        alpha: Int = 255,
        spacing: Float = 0f,
        centred: Boolean = false,
    ) {
        text.typeface = face
        text.textSize = size
        text.letterSpacing = spacing / size
        text.textAlign = if (centred) Paint.Align.CENTER else Paint.Align.LEFT
        text.color = color
        text.alpha = alpha
        canvas.drawText(value, x, text.baselineInBox(top, box), text)
    }

    /** Dim track plus an accent arc from 12 o'clock for the seconds. */
    private fun ring(canvas: Canvas, second: Int, accent: Int) {
        val c = ARTBOARD / 2
        line.strokeWidth = 4f
        line.color = TRACK
        canvas.drawCircle(c, c, RING_RADIUS, line)
        line.color = accent
        canvas.drawArc(
            c - RING_RADIUS, c - RING_RADIUS, c + RING_RADIUS, c + RING_RADIUS,
            -90f, maxOf(second.toFloat(), 0.2f) * 6, false, line,
        )
    }

    /** A 24 x 24 line icon, [size] wide, with its left edge at [x] and centred on [cy]. */
    private fun drawIcon(canvas: Canvas, path: Path, x: Float, cy: Float, size: Float, color: Int) {
        canvas.save()
        canvas.translate(x, cy - size / 2)
        canvas.scale(size / 24, size / 24)
        line.strokeWidth = 2f
        line.color = color
        canvas.drawPath(path, line)
        canvas.restore()
    }

    private fun icon(data: String): Path = PathParser.createPathFromPathData(data)

    private companion object {
        const val ARTBOARD = 480f
        const val TIME_SIZE = 194.3f
        const val DIGIT_SCALE = 0.70f
        const val DIGIT_ADVANCE = 0.44f
        const val TIME_CENTRE = 177f
        const val HOURS_BASELINE = 230f
        const val MINUTES_BASELINE = 378f
        const val COLUMN = 276f
        const val RING_RADIUS = 234f

        val WHITE = Color.parseColor("#f2f2f2")
        val GREY = Color.parseColor("#9a9a9a")
        val TRACK = Color.parseColor("#161616")
        val DIVIDER = Color.parseColor("#262626")
        val PILL = Color.parseColor("#2a2a2a")
        val SUN = Color.parseColor("#ffc24d")
        val HEART = Color.parseColor("#ff4d6d")
        val BATTERY = Color.parseColor("#b6f35b")
        val AMBIENT_HOURS = Color.parseColor("#d0d0d0")
        val AMBIENT_MINUTES = Color.parseColor("#7a7a7a")
    }
}
