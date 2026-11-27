package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import java.time.ZonedDateTime

/**
 * Terminal — solid hours over outlined minutes, a column of labelled readings, the date on
 * top and a prompt line with a blinking cursor at the bottom.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (terminal). Sunrise,
 * weather condition and the next event come from the watch itself, so the preview shows
 * placeholders for them.
 *
 * Ambient: outlined grey digits and a dimmed date only.
 */
class TerminalPainter(assets: AssetManager) : FacePainter {

    private val mono = Fonts.static(assets, Fonts.JETBRAINS_MONO)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = mono }
    private val digit = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Fonts.get(assets, Fonts.SPACE_GROTESK, 700)
        textSize = DIGIT_SIZE
        textAlign = Paint.Align.CENTER
        fontFeatureSettings = "'tnum'"
        strokeWidth = 2f
    }
    private val outline = Path()

    /** Tabular digit advance, and the cell width left after the design's -0.06em tracking. */
    private val advance = digit.measureText("0")
    private val cell = advance - 0.06f * DIGIT_SIZE
    private val digitsLeft = DESIGN_SIZE / 2 - (2 * cell + COLUMN_GAP + COLUMN_WIDTH) / 2
    private val column = digitsLeft + 2 * cell + COLUMN_GAP

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

        digits(canvas, time.displayHour(data.is24Hour).pad2(), 0, if (ambient) AMBIENT_HOURS else WHITE, ambient)
        digits(canvas, time.minute.pad2(), 1, if (ambient) AMBIENT_MINUTES else accent, true)

        val date = "${time.dayShort()} ${time.dayOfMonth.pad2()} ${time.monthShort()} ${time.year}"
        val dateWidth = date.length * (0.6f * 12 + 2.64f)
        label(canvas, date, (DESIGN_SIZE - dateWidth) / 2, TOP, 12f, GREY, 2.64f, if (ambient) 160 else 255)

        if (!ambient) {
            reading(canvas, 0, "WEATHER", data.temperatureC?.let { "$it°" } ?: "--°", WHITE)
            reading(canvas, 1, "SUN", "--:--", WHITE)
            reading(canvas, 2, "HEART", "${data.heartRate ?: "--"} BPM", HEART)
            reading(canvas, 3, "BATTERY", "${data.battery}%", BATTERY)
            prompt(canvas, "NO EVENTS", time.second % 2 == 1, accent)
        }
        canvas.restore()
    }

    /** Two digits in row 0 (hours) or 1 (minutes), solid or outlined. */
    private fun digits(canvas: Canvas, value: String, row: Int, color: Int, outlined: Boolean) {
        digit.color = color
        digit.style = if (outlined) Paint.Style.STROKE else Paint.Style.FILL
        val baseline = digit.baselineInBox(MIDDLE + row * DIGIT_LINE, DIGIT_LINE)
        value.forEachIndexed { i, c ->
            val x = digitsLeft + i * cell + advance / 2
            if (outlined) {
                digit.getTextPath(c.toString(), 0, 1, x, baseline, outline)
                // Merge overlapping contours so no inner lines are stroked.
                outline.op(outline, Path.Op.UNION)
                canvas.drawPath(outline, digit)
            } else {
                canvas.drawText(c.toString(), x, baseline, digit)
            }
        }
    }

    /** One block of the reading column: a small label over its value. */
    private fun reading(canvas: Canvas, index: Int, name: String, value: String, color: Int) {
        text.textSize = 11f
        val labelHeight = text.lineHeight()
        text.textSize = 16f
        val height = labelHeight + 2 + text.lineHeight()
        val top = MIDDLE + (2 * DIGIT_LINE - (4 * height + 3 * 13)) / 2 + index * (height + 13)
        label(canvas, name, column, top, 11f, GREY, 1.1f)
        label(canvas, value, column, top + labelHeight + 2, 16f, color, 1.1f)
    }

    /** ">_ message" and the cursor, centred as one line. */
    private fun prompt(canvas: Canvas, message: String, cursor: Boolean, accent: Int) {
        val char = 11 * 0.6f + PROMPT_SPACING
        val left = (DESIGN_SIZE - ((2 + message.length) * char + 8 + 8 + 7)) / 2
        label(canvas, ">_", left, BOTTOM, 11f, accent, PROMPT_SPACING)
        label(canvas, message, left + 2 * char + 8, BOTTOM, 11f, SOFT, PROMPT_SPACING)
        if (cursor) {
            text.color = accent
            val x = left + (2 + message.length) * char + 16
            canvas.drawRect(x, BOTTOM, x + 7, BOTTOM + 13, text)
        }
    }

    /** Left-aligned text whose CSS "normal" line box starts at [top]; [spacing] is in px. */
    private fun label(
        canvas: Canvas,
        value: String,
        x: Float,
        top: Float,
        size: Float,
        color: Int,
        spacing: Float,
        alpha: Int = 255,
    ) {
        text.textSize = size
        text.letterSpacing = spacing / size
        text.color = color
        text.alpha = alpha
        // Android centres tracking around each glyph; CSS adds it after.
        canvas.drawText(value, x - spacing / 2, top - text.fontMetrics.ascent, text)
    }

    private companion object {
        const val DIGIT_SIZE = 132f
        const val DIGIT_LINE = 0.82f * DIGIT_SIZE
        const val COLUMN_WIDTH = 85.6f
        const val COLUMN_GAP = 22f
        const val TOP = 89.6f
        const val MIDDLE = TOP + 15.84f + 12
        const val BOTTOM = MIDDLE + 2 * DIGIT_LINE + 12
        const val PROMPT_SPACING = 11 * 0.12f

        val WHITE = Color.parseColor("#f2f4f7")
        val GREY = Color.parseColor("#9aa0a8")
        val SOFT = Color.parseColor("#c9ced4")
        val HEART = Color.parseColor("#ff6b7a")
        val BATTERY = Color.parseColor("#c6ff3d")
        val AMBIENT_HOURS = Color.parseColor("#d0d0d0")
        val AMBIENT_MINUTES = Color.parseColor("#7a7a7a")
    }
}
