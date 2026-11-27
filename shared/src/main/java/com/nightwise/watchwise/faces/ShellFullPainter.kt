package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import java.time.ZonedDateTime
import java.util.Locale
import java.util.TimeZone
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Shell Full — Shell Window redesigned for the whole round screen: no window box, just the
 * terminal lines (`date`, `status`, `next`) as large as fit.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (shell_full), laid out
 * on the 450 x 450 face. Lines share one left margin, stepped in on the first and last rows
 * where the bezel curves. The next event and unread count come from the watch itself (a
 * complication and a WFF data source), so the preview shows a placeholder line.
 *
 * Ambient: seconds and cursor off, everything else dimmed.
 */
class ShellFullPainter(assets: AssetManager) : FacePainter {

    private val regular = Fonts.static(assets, Fonts.JETBRAINS_MONO)
    private val extraBold = Fonts.static(assets, Fonts.JETBRAINS_MONO_EXTRABOLD)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)

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
        val textAlpha = if (ambient) 170 else 255

        fun span(row: Int, column: Int, str: String, color: Int) {
            text.typeface = regular
            text.textSize = BODY
            text.color = color
            text.alpha = textAlpha
            canvas.drawText(str, left(row) + column * COL, baseline(rowTop(row)), text)
        }

        fun prompt(row: Int, cmd: String) {
            span(row, 0, "watch:~$", accent)
            span(row, 9, cmd, GREEN)
        }

        prompt(P_DATE, "date")

        // Time row: HH:MM, then :SS on the same baseline.
        val timeTop = rowTop(TIME_ROW) + 2
        val timeBaseline = timeTop + TIME * (1 - 1.32f) / 2 + TIME * 1.02f
        text.typeface = extraBold
        text.textSize = TIME
        text.color = TIME_TEXT
        text.alpha = if (ambient) 230 else 255
        canvas.drawText("${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}", LEFT, timeBaseline, text)
        if (!ambient) {
            text.textSize = SECS
            text.color = DIM
            canvas.drawText(":${time.second.pad2()}", LEFT + 5 * 0.6f * TIME + 3, timeBaseline, text)
        }

        val zone = TimeZone.getTimeZone(time.zone)
        val tz = zone.getDisplayName(zone.inDaylightTime(java.util.Date.from(time.toInstant())), TimeZone.SHORT, Locale.getDefault())
        val day = time.dayShort().lowercase().replaceFirstChar { it.uppercase() }
        val month = time.monthShort().lowercase().replaceFirstChar { it.uppercase() }
        span(DATE_ROW, 0, "$day, ${time.dayOfMonth} $month ${time.year} · $tz", DATE)
        prompt(DATE_ROW + 1, "status")
        span(DATE_ROW + 2, 0, "✓ Battery", TEXT)
        span(DATE_ROW + 2, 10, "${data.battery}%", GREEN)
        span(DATE_ROW + 3, 0, "✓ HR", TEXT)
        span(DATE_ROW + 3, 5, "${data.heartRate ?: "--"} bpm", RED)
        val steps = data.steps
        span(DATE_ROW + 4, 0, "✓ Steps ${steps?.let { "%,d".format(Locale.US, it) } ?: "--"}", TEXT)
        span(
            DATE_ROW + 5, 0,
            if (steps == null) "✓ -- kcal · -- km"
            else "✓ ${data.calories} kcal · ${steps * 762 / 1_000_000}.${steps * 762 / 100_000 % 10} km",
            TEXT,
        )
        span(DATE_ROW + 6, 0, data.temperatureC?.let { "✓ $it°C" } ?: "✓ Weather --", TEXT)
        prompt(DATE_ROW + 7, "next")
        span(DATE_ROW + 8, 0, "→ no events", TEXT)
        val last = DATE_ROW + 9
        prompt(last, "npm")

        if (!ambient && time.second % 2 == 0) {
            // Design: 8 x 15 block at 13px text, its bottom 3px below the baseline.
            fill.color = CURSOR
            val x = left(last) + 13 * COL
            val bottom = baseline(rowTop(last)) + BODY * 3 / 13
            canvas.drawRect(x, bottom - BODY * 15 / 13, x + BODY * 8 / 13, bottom, fill)
        }
        canvas.restore()
    }

    /** Top of row [i]: rows 0 and 2+ are body lines, row 1 is the time. */
    private fun rowTop(i: Int): Float = FIRST_TOP + i * LINE + if (i > TIME_ROW) TIME + 4 - LINE else 0f

    /** The common left margin, stepped in to stay [EDGE] inside the circle. */
    private fun left(row: Int): Float {
        val top = rowTop(row)
        val c = DESIGN_SIZE / 2
        val worst = max(abs(top - c), abs(top + LINE - c))
        val half = sqrt(max(0f, c * c - worst * worst))
        return max(LEFT, c - half + EDGE)
    }

    /** Baseline of a body line in a [LINE]-high row (JetBrains Mono: ascent 1.02em, descent 0.30em). */
    private fun baseline(top: Float): Float = top + (LINE - 1.32f * BODY) / 2 + 1.02f * BODY

    private companion object {
        const val BODY = 19f
        const val LINE = 25f
        const val TIME = 80f
        const val SECS = 30f
        const val COL = 0.6f * BODY
        const val LEFT = 82f
        const val EDGE = 8f
        const val P_DATE = 0
        const val TIME_ROW = 1
        const val DATE_ROW = 2
        const val ROWS = 12
        const val FIRST_TOP = (DESIGN_SIZE - (ROWS - 1) * LINE - (TIME + 4)) / 2

        val TEXT = Color.parseColor("#e6e6e6")
        val TIME_TEXT = Color.parseColor("#f2f2f2")
        val DATE = Color.parseColor("#b5b5b5")
        val DIM = Color.parseColor("#9a9a9a")
        val GREEN = Color.parseColor("#5fd77a")
        val RED = Color.parseColor("#ff6b81")
        val CURSOR = Color.parseColor("#d0d0d0")
    }
}
