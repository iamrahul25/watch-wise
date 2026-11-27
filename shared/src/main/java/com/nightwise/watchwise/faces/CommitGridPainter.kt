package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import java.time.ZonedDateTime
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.cos
import kotlin.math.sin

/**
 * Commit Grid — a minute ring of "commit" dots, a shell prompt, status badges and a
 * contribution-style grid that fills as today's step goal is reached.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (commit_grid). The
 * previews have no step goal to read, so they assume 10,000.
 */
class CommitGridPainter(assets: AssetManager) : FacePainter {

    private val mono = Fonts.static(assets, Fonts.JETBRAINS_MONO)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = mono }
    private val shape = Paint(Paint.ANTI_ALIAS_FLAG)
    private val box = RectF()
    private val topArc = arc(TOP_RADIUS, -145f, 110f)
    private val bottomArc = arc(BOTTOM_RADIUS, 145f, -110f)
    private val levels = shades()

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

        val steps = data.steps ?: 0
        ring(canvas, time.minute, accent, ambient)

        val clock = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        words(canvas, clock, 220f, 182.5f, 77.5f, WHITE, Paint.Align.CENTER, if (ambient) 210 else 255)
        val day = time.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.US)
        val month = time.month.getDisplayName(TextStyle.SHORT, Locale.US)
        val date = "$day, ${time.dayOfMonth} $month ${time.year}"
        words(canvas, date, CENTER, 212.5f, 16.25f, GREY, Paint.Align.CENTER, if (ambient) 160 else 255)

        grid(canvas, steps, accent, ambient)

        if (!ambient) {
            dot(canvas, time.second * 6f, 7.5f, SECOND)
            words(canvas, ":${time.second.pad2()}", 341f, 182.5f, 20f, accent)
            prompt(canvas, accent)
            info(canvas)
            badges(canvas, data)
            val commits = steps / 1000
            val word = if (commits == 1) "commit" else "commits"
            curved(canvas, "main · $commits $word today", topArc, GREY)
            val km = (steps * 0.00762).toInt()
            val summary = "${steps * 100L / GOAL}% of goal · ${km / 10}.${km % 10} km"
            curved(canvas, summary, bottomArc, MUTED)
        }
        canvas.restore()
    }

    /** Minute progress around the edge, with a dot every five minutes. */
    private fun ring(canvas: Canvas, minute: Int, accent: Int, ambient: Boolean) {
        shape.style = Paint.Style.STROKE
        shape.strokeCap = Paint.Cap.ROUND
        box.set(CENTER - RING, CENTER - RING, CENTER + RING, CENTER + RING)
        if (!ambient) {
            shape.color = TRACK
            shape.strokeWidth = 2.5f
            canvas.drawOval(box, shape)
        }
        shape.color = accent
        shape.alpha = if (ambient) 90 else 205
        shape.strokeWidth = 3.2f
        canvas.drawArc(box, -90f, minute * 6f, false, shape)

        if (!ambient) {
            for (i in 0 until 12) {
                val done = minute >= i * 5
                dot(canvas, i * 30f, 13.75f, if (done) accent else DOT)
                dot(canvas, i * 30f, 8.75f, Color.BLACK)
                if (done) dot(canvas, i * 30f, 4f, accent)
            }
        }
        val alpha = if (ambient) 110 else 255
        dot(canvas, minute * 6f, 23f, accent, alpha)
        dot(canvas, minute * 6f, 16.8f, Color.BLACK)
        dot(canvas, minute * 6f, 8.75f, accent, alpha)
    }

    /** A circle of diameter [size] on the minute ring, [degrees] clockwise from the top. */
    private fun dot(canvas: Canvas, degrees: Float, size: Float, color: Int, alpha: Int = 255) {
        val a = Math.toRadians(degrees.toDouble())
        shape.style = Paint.Style.FILL
        shape.color = color
        shape.alpha = alpha
        canvas.drawCircle(
            CENTER + RING * sin(a).toFloat(), CENTER - RING * cos(a).toFloat(), size / 2, shape,
        )
    }

    /** The info icon; on the watch, tapping it opens the guide to the readings. */
    private fun info(canvas: Canvas) {
        shape.style = Paint.Style.STROKE
        shape.strokeWidth = 2f
        shape.color = GREY
        canvas.drawCircle(INFO_X, INFO_Y, 10f, shape)
        shape.style = Paint.Style.FILL
        canvas.drawCircle(INFO_X, INFO_Y - 4.5f, 1.6f, shape)
        rounded(canvas, INFO_X - 1.25f, INFO_Y - 1.5f, 2.5f, 7.5f, 1.25f, GREY)
    }

    private fun prompt(canvas: Canvas, accent: Int) {
        val char = 0.6f * 15
        val left = CENTER - 17 * char / 2
        words(canvas, "user@watch", left, 105f, 15f, accent)
        words(canvas, ":~", left + 10 * char, 105f, 15f, GREY)
        words(canvas, "$ now", left + 12 * char, 105f, 15f, WHITE)
    }

    private fun badges(canvas: Canvas, data: FaceData) {
        row(
            canvas, 232.5f,
            Badge("battery", "${data.battery}%", 4, BATTERY),
            Badge("steps", data.steps?.let { String.format(Locale.US, "%,d", it) } ?: "--", 6, STEPS),
        )
        row(
            canvas, 262.5f,
            Badge("bpm", data.heartRate?.toString() ?: "--", 3, HEART),
            Badge("temp", data.temperatureC?.let { "$it°C" } ?: "--", 5, TEMPERATURE),
        )
    }

    private class Badge(val label: String, val value: String, chars: Int, val color: Int) {
        val labelWidth = label.length * CHAR + 12.5f
        val valueWidth = chars * CHAR + 12.5f
    }

    /** Badges side by side, centred as one row. */
    private fun row(canvas: Canvas, top: Float, vararg badges: Badge) {
        val width = badges.sumOf { (it.labelWidth + it.valueWidth).toDouble() }.toFloat() +
            10 * (badges.size - 1)
        var x = CENTER - width / 2
        for (b in badges) {
            val split = x + b.labelWidth
            rounded(canvas, x, top, b.labelWidth + b.valueWidth, 22.5f, 5f, b.color)
            rounded(canvas, x, top, b.labelWidth, 22.5f, 5f, LABEL_BG)
            rounded(canvas, split - 6, top, 6f, 22.5f, 0f, LABEL_BG)
            words(canvas, b.label, x + b.labelWidth / 2, top + 16.25f, TEXT, LABEL, Paint.Align.CENTER)
            words(canvas, b.value, split + b.valueWidth / 2, top + 16.25f, TEXT, Color.WHITE, Paint.Align.CENTER)
            x = split + b.valueWidth + 10
        }
    }

    /** 13 x 7 cells filled column by column up to today's share of the step goal. */
    private fun grid(canvas: Canvas, steps: Int, accent: Int, ambient: Boolean) {
        val filled = (steps.toLong() * CELLS / GOAL).toInt()
        val alpha = if (ambient) 90 else 255
        for (i in 0 until CELLS) {
            val x = GRID_X + (i / ROWS) * STEP
            val y = GRID_Y + (i % ROWS) * STEP
            rounded(canvas, x, y, CELL, CELL, 2f, CELL_BG, alpha)
            if (i < filled) rounded(canvas, x, y, CELL, CELL, 2f, accent, LEVELS[levels[i]] * alpha / 255)
        }
        val current = filled.coerceIn(0, CELLS - 1)
        val x = GRID_X + (current / ROWS) * STEP
        val y = GRID_Y + (current % ROWS) * STEP
        shape.style = Paint.Style.STROKE
        shape.strokeWidth = 1.5f
        shape.color = WHITE
        shape.alpha = alpha
        canvas.drawRoundRect(x, y, x + CELL, y + CELL, 2f, 2f, shape)
    }

    private fun rounded(
        canvas: Canvas, x: Float, y: Float, w: Float, h: Float, r: Float, color: Int, alpha: Int = 255,
    ) {
        shape.style = Paint.Style.FILL
        shape.color = color
        shape.alpha = alpha
        canvas.drawRoundRect(x, y, x + w, y + h, r, r, shape)
    }

    private fun words(
        canvas: Canvas,
        value: String,
        x: Float,
        baseline: Float,
        size: Float,
        color: Int,
        align: Paint.Align = Paint.Align.LEFT,
        alpha: Int = 255,
    ) {
        text.textSize = size
        text.textAlign = align
        text.color = color
        text.alpha = alpha
        canvas.drawText(value, x, baseline, text)
    }

    /** Text centred along [path]. */
    private fun curved(canvas: Canvas, value: String, path: Path, color: Int) {
        text.textSize = TEXT
        text.textAlign = Paint.Align.CENTER
        text.color = color
        canvas.drawTextOnPath(value, path, 0f, 0f, text)
    }

    private fun arc(radius: Float, start: Float, sweep: Float) = Path().apply {
        addArc(CENTER - radius, CENTER - radius, CENTER + radius, CENTER + radius, start, sweep)
    }

    /** The design's pseudo-random shade (0..3) of every cell; matches cg_levels() in the generator. */
    private fun shades(): IntArray {
        var seed = 7
        return IntArray(CELLS) {
            seed = (seed * 9301 + 49297) % 233280
            val v = seed / 233280.0
            if (v < 0.3) 0 else if (v < 0.55) 1 else if (v < 0.8) 2 else 3
        }
    }

    private companion object {
        const val CENTER = DESIGN_SIZE / 2
        const val RING = 203.75f
        const val TOP_RADIUS = 182.5f
        const val BOTTOM_RADIUS = 190f
        const val ROWS = 7
        const val CELLS = 13 * ROWS
        const val CELL = 10f
        const val STEP = 12.5f
        const val GRID_X = CENTER - (13 * STEP - (STEP - CELL)) / 2
        const val GRID_Y = 297f
        const val GOAL = 10_000
        const val TEXT = 13.75f
        const val INFO_X = 342f
        const val INFO_Y = 328f
        const val CHAR = 0.6f * TEXT
        val LEVELS = intArrayOf(80, 130, 190, 255)

        val WHITE = Color.parseColor("#e6edf3")
        val GREY = Color.parseColor("#8b949e")
        val MUTED = Color.parseColor("#6e7681")
        val CELL_BG = Color.parseColor("#111418")
        val TRACK = Color.parseColor("#21262d")
        val DOT = Color.parseColor("#30363d")
        val SECOND = Color.parseColor("#f78166")
        val LABEL_BG = Color.parseColor("#30363d")
        val LABEL = Color.parseColor("#c9d1d9")
        val BATTERY = Color.parseColor("#238636")
        val STEPS = Color.parseColor("#1f6feb")
        val HEART = Color.parseColor("#da3633")
        val TEMPERATURE = Color.parseColor("#bd561d")
    }
}
