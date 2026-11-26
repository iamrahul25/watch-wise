package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import java.time.ZonedDateTime
import java.util.Locale
import java.util.TimeZone

/**
 * 05 · Shell Window — a terminal window running `date`, `status` and `next`.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (shell_window), which
 * follows the design's 480 x 480 artboard. JetBrains Mono is monospaced, so every span is
 * placed by column. The next event and unread count come from the watch itself (a
 * complication and a WFF data source), so the preview shows a placeholder line.
 *
 * Ambient: window fills, seconds and cursor off; frame and text dimmed.
 */
class ShellWindowPainter(assets: AssetManager) : FacePainter {

    private val regular = Fonts.static(assets, Fonts.JETBRAINS_MONO)
    private val extraBold = Fonts.static(assets, Fonts.JETBRAINS_MONO_EXTRABOLD)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val rect = RectF()

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

        val frameAlpha = if (ambient) 110 else 255
        val textAlpha = if (ambient) 170 else 255

        // Window.
        val bodyY = WIN_Y + 1 + TITLE_H
        if (!ambient) {
            fill.color = TITLE_BG
            rect.set(WIN_X, WIN_Y, WIN_X + WIN_W, WIN_Y + WIN_H)
            canvas.drawRoundRect(rect, 12f, 12f, fill)
            fill.color = BODY_BG
            rect.set(WIN_X + 1, bodyY, WIN_X + WIN_W - 1, WIN_Y + WIN_H - 1)
            canvas.drawRoundRect(rect, 11f, 11f, fill)
            canvas.drawRect(WIN_X + 1, bodyY, WIN_X + WIN_W - 1, bodyY + 12, fill)
        }
        stroke.color = BORDER
        stroke.alpha = frameAlpha
        stroke.strokeWidth = 1f
        rect.set(WIN_X + 0.5f, WIN_Y + 0.5f, WIN_X + WIN_W - 0.5f, WIN_Y + WIN_H - 0.5f)
        canvas.drawRoundRect(rect, 11.5f, 11.5f, stroke)
        LIGHTS.forEachIndexed { i, c ->
            fill.color = c
            fill.alpha = frameAlpha
            canvas.drawCircle(WIN_X + 1 + 12 + 5.5f + i * 18, WIN_Y + 1 + TITLE_H / 2, 5.5f, fill)
        }
        fill.alpha = 255
        text.typeface = regular
        text.textSize = 11f
        text.letterSpacing = 0f
        text.textAlign = Paint.Align.CENTER
        text.color = TITLE_TEXT
        text.alpha = frameAlpha
        canvas.drawText("watch — bash", WIN_X + WIN_W / 2, baseline(11f, WIN_Y + 1 + (TITLE_H - LINE) / 2), text)
        text.textAlign = Paint.Align.LEFT

        // Lines.
        fun span(row: Float, column: Int, str: String, color: Int) {
            text.typeface = regular
            text.textSize = BODY
            text.letterSpacing = 0f
            text.color = color
            text.alpha = textAlpha
            canvas.drawText(str, LEFT + column * COL, baseline(BODY, row), text)
        }

        fun prompt(row: Float, cmd: String) {
            span(row, 0, "watch:~$", accent)
            span(row, 9, cmd, GREEN)
        }

        prompt(TOP, "date")

        // Time row.
        val timeBaseline = TIME_ROW + TIME * (1 - 1.32f) / 2 + TIME * 1.02f
        text.typeface = extraBold
        text.textSize = TIME
        text.letterSpacing = 0f // the design's -2px tracking is left out, as in the WFF face
        text.color = TIME_TEXT
        text.alpha = if (ambient) 230 else 255
        val hm = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        canvas.drawText(hm, LEFT, timeBaseline, text)
        if (!ambient) {
            val hmWidth = 5 * 0.6f * TIME
            text.textSize = SECS
            text.letterSpacing = 0f
            text.color = DIM
            canvas.drawText(":${time.second.pad2()}", LEFT + hmWidth + 3, timeBaseline, text)
        }

        val tz = TimeZone.getTimeZone(time.zone).getDisplayName(
            TimeZone.getTimeZone(time.zone).inDaylightTime(java.util.Date.from(time.toInstant())),
            TimeZone.SHORT, Locale.getDefault(),
        )
        val day = time.dayShort().lowercase().replaceFirstChar { it.uppercase() }
        val month = time.monthShort().lowercase().replaceFirstChar { it.uppercase() }
        span(row(0), 0, "$day, ${time.dayOfMonth} $month ${time.year} · $tz", DATE)
        prompt(row(1), "status")
        span(row(2), 0, "✓ Battery", TEXT)
        span(row(2), 10, "${data.battery}%", GREEN)
        span(row(3), 0, "✓ HR", TEXT)
        span(row(3), 5, "${data.heartRate ?: "--"} bpm", RED)
        val steps = data.steps
        span(row(4), 0, "✓ Steps ${steps?.let { "%,d".format(Locale.US, it) } ?: "--"} / 10,000", TEXT)
        span(
            row(5), 0,
            if (steps == null) "✓ -- kcal · -- km"
            else "✓ ${data.calories} kcal · ${steps * 762 / 1_000_000}.${steps * 762 / 100_000 % 10} km",
            TEXT,
        )
        span(row(6), 0, data.temperatureC?.let { "✓ $it°C" } ?: "✓ Weather --", TEXT)
        prompt(row(7), "next")
        span(row(8), 0, "→ no events", TEXT)
        prompt(row(9), "npm")

        if (!ambient && time.second % 2 == 0) {
            fill.color = CURSOR
            val x = LEFT + 13 * COL
            val y = baseline(BODY, row(9)) + 3 - 15
            canvas.drawRect(x, y, x + 8, y + 15, fill)
        }
        canvas.restore()
    }

    /** Baseline of a [size] line centred in a [LINE]-high row starting at [top] (CSS line box). */
    private fun baseline(size: Float, top: Float): Float {
        // JetBrains Mono: ascent 1.02em, descent 0.30em, no line gap.
        return top + (LINE - 1.32f * size) / 2 + 1.02f * size
    }

    private fun row(i: Int) = TIME_ROW + TIME + 2 + i * LINE

    private companion object {
        const val ARTBOARD = 480f
        const val WIN_X = 68f
        const val WIN_Y = 92f
        const val WIN_W = 344f
        const val TITLE_H = 30f
        const val LINE = 19f
        const val BODY = 13f
        const val TIME = 46f
        const val SECS = 20f
        const val COL = 0.6f * BODY
        const val LEFT = WIN_X + 1 + 14
        const val TOP = WIN_Y + 1 + TITLE_H + 10
        const val TIME_ROW = TOP + LINE + 4
        const val WIN_H = TIME_ROW + TIME + 2 + 10 * LINE + 12 + 1 - WIN_Y

        val TITLE_BG = Color.parseColor("#232323")
        val BODY_BG = Color.parseColor("#161616")
        val BORDER = Color.parseColor("#2c2c2c")
        val TITLE_TEXT = Color.parseColor("#a8a8a8")
        val TEXT = Color.parseColor("#e6e6e6")
        val TIME_TEXT = Color.parseColor("#f2f2f2")
        val DATE = Color.parseColor("#b5b5b5")
        val DIM = Color.parseColor("#9a9a9a")
        val GREEN = Color.parseColor("#5fd77a")
        val RED = Color.parseColor("#ff6b81")
        val CURSOR = Color.parseColor("#d0d0d0")
        val LIGHTS = intArrayOf(
            Color.parseColor("#ff5f57"), Color.parseColor("#febc2e"), Color.parseColor("#28c840"),
        )
    }
}
