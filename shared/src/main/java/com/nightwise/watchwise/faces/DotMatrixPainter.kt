package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import java.time.ZonedDateTime
import kotlin.math.cos
import kotlin.math.sin

/**
 * 03 · Dot Matrix — fitness.
 *
 * An LED board centred on the screen: HH:MM in big 5 x 7 dot digits (hours white, minutes in
 * the accent) over their unlit dots, a ring of 60 dots counting the seconds, the battery and
 * date above and steps, calories and heart rate below.
 *
 * Ambient (always-on, AMOLED): thinner dots for the time, with only the date and the battery
 * percentage, everything dimmed.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (dot_matrix, DM_*).
 */
class DotMatrixPainter(assets: AssetManager) : FacePainter {

    private val black = Fonts.get(assets, Fonts.DOTO, 900)

    private val dots = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG)

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

        if (!ambient) {
            for (first in DIGIT_COLUMNS) {
                for (row in 0 until 7) for (col in 0 until 5) timeDot(canvas, first + col, row, PITCH_DOT, UNLIT)
            }
            secondsRing(canvas, time.second, accent)
        }
        time(canvas, time, data, accent, ambient)
        date(canvas, time, accent, ambient)
        words(canvas, "${data.battery}%", CENTRE, 83f, 21f, if (ambient) AMBIENT_GREY else PERCENT_GREY)
        if (!ambient) {
            battery(canvas, data.battery, accent)
            stats(canvas, data, accent)
        }
        canvas.restore()
    }

    private fun time(canvas: Canvas, time: ZonedDateTime, data: FaceData, accent: Int, ambient: Boolean) {
        val value = time.displayHour(data.is24Hour).pad2() + time.minute.pad2()
        val diameter = if (ambient) AMBIENT_DOT else PITCH_DOT
        value.forEachIndexed { k, digit ->
            val color = when {
                ambient -> if (k < 2) AMBIENT_HOURS else AMBIENT_MINUTES
                k < 2 -> Color.WHITE
                else -> accent
            }
            DIGITS[digit - '0'].forEachIndexed { row, line ->
                line.forEachIndexed { col, cell ->
                    if (cell == '#') timeDot(canvas, DIGIT_COLUMNS[k] + col, row, diameter, color)
                }
            }
        }
        val colon = if (ambient) AMBIENT_COLON else LABEL_GREY
        timeDot(canvas, 12, 2, diameter, colon)
        timeDot(canvas, 12, 4, diameter, colon)
    }

    /** One dot of the time grid: column 12 is the middle of the screen, as is row 3. */
    private fun timeDot(canvas: Canvas, column: Int, row: Int, diameter: Float, color: Int) =
        dot(canvas, CENTRE + (column - 12) * PITCH, CENTRE + (row - 3) * PITCH, diameter, color)

    private fun dot(canvas: Canvas, x: Float, y: Float, diameter: Float, color: Int) {
        dots.color = color
        canvas.drawCircle(x, y, diameter / 2, dots)
    }

    private fun secondsRing(canvas: Canvas, second: Int, accent: Int) {
        for (i in 0 until 60) {
            val angle = i * Math.PI / 30
            val x = CENTRE + (RING_RADIUS * sin(angle)).toFloat()
            val y = CENTRE - (RING_RADIUS * cos(angle)).toFloat()
            val diameter = if (i == second) 10f else if (i % 5 == 0) 7.5f else 5f
            val color = if (i == second) Color.WHITE else if (i < second) accent else RING_UNLIT
            dot(canvas, x, y, diameter, color)
        }
    }

    /** "SUN 22 NOV" with the day name in the accent. */
    private fun date(canvas: Canvas, time: ZonedDateTime, accent: Int, ambient: Boolean) {
        val column = 0.6f * 29
        val left = CENTRE - 10 * column / 2
        val alpha = if (ambient) 150 else 255
        words(canvas, time.dayShort(), left, 122f, 29f, accent, black, Paint.Align.LEFT, alpha)
        val rest = "${time.dayOfMonth.pad2()} ${time.monthShort()}"
        words(canvas, rest, left + 4 * column, 122f, 29f, Color.WHITE, black, Paint.Align.LEFT, alpha)
    }

    private fun battery(canvas: Canvas, percent: Int, accent: Int) {
        for (i in 0 until 10) {
            val color = if (percent >= i * 10 + 5) accent else BATTERY_UNLIT
            dot(canvas, CENTRE + (i - 4.5f) * 13, 58f, 8f, color)
        }
    }

    private fun stats(canvas: Canvas, data: FaceData, accent: Int) {
        val values = listOf(data.steps, data.calories, data.heartRate)
        for (i in 0 until 3) {
            val x = STAT_COLUMNS[i]
            ICONS[i].forEachIndexed { row, line ->
                line.forEachIndexed { col, cell ->
                    if (cell == '#') {
                        dot(canvas, x + (col - 3) * ICON_PITCH, 318f + (row - 3) * ICON_PITCH, ICON_PITCH * 0.92f, accent)
                    }
                }
            }
            number(canvas, values[i]?.toString() ?: "--", x, 354f)
            words(canvas, LABELS[i], x, 386f, 17f, LABEL_GREY)
        }
    }

    /** A reading in small dot digits, centred on ([x], [y]). */
    private fun number(canvas: Canvas, value: String, x: Float, y: Float) {
        val left = x - (value.length * 6 - 1) * VALUE_PITCH / 2
        value.forEachIndexed { k, ch ->
            val rows = if (ch == '-') DASH else DIGITS[ch - '0']
            rows.forEachIndexed { row, line ->
                line.forEachIndexed { col, cell ->
                    if (cell == '#') {
                        val dx = left + (k * 6 + col + 0.5f) * VALUE_PITCH
                        dot(canvas, dx, y + (row - 3) * VALUE_PITCH, VALUE_PITCH * PITCH_DOT / PITCH, Color.WHITE)
                    }
                }
            }
        }
    }

    /** Text centred on [y] (by its capital height), starting at or centred on [x]. */
    private fun words(
        canvas: Canvas,
        value: String,
        x: Float,
        y: Float,
        size: Float,
        color: Int,
        font: Typeface = black,
        align: Paint.Align = Paint.Align.CENTER,
        alpha: Int = 255,
    ) {
        text.typeface = font
        text.textSize = size
        text.textAlign = align
        text.color = color
        text.alpha = alpha
        canvas.drawText(value, x, y + 0.35f * size, text)
    }

    private companion object {
        const val CENTRE = 225f
        const val PITCH = 15f
        const val PITCH_DOT = 12.6f
        const val AMBIENT_DOT = 8f
        const val RING_RADIUS = 213.0
        const val ICON_PITCH = 4.4f
        const val VALUE_PITCH = 3f
        val DASH = "..... ..... ..... .###. ..... ..... .....".split(' ')
        val DIGIT_COLUMNS = intArrayOf(0, 6, 14, 20)
        val STAT_COLUMNS = floatArrayOf(127f, 225f, 323f)
        val LABELS = arrayOf("STEPS", "KCAL", "BPM")

        // The 5 x 7 digits and 7 x 7 icons of DM_DIGITS / DM_ICONS in the generator.
        val DIGITS = listOf(
            ".###. #...# #...# #...# #...# #...# .###.", "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
            ".###. #...# ....# ...#. ..#.. .#... #####", "####. ....# ....# .###. ....# ....# ####.",
            "...#. ..##. .#.#. #..#. ##### ...#. ...#.", "##### #.... ####. ....# ....# #...# .###.",
            "..##. .#... #.... ####. #...# #...# .###.", "##### ....# ...#. ..#.. .#... .#... .#...",
            ".###. #...# #...# .###. #...# #...# .###.", ".###. #...# #...# .#### ....# ...#. .##..",
        ).map { it.split(' ') }
        val ICONS = listOf(
            "...##.. ...##.. ..###.. .#.##.. ...###. ..#..#. .#...#.",
            "...#... ..##... ..###.. .####.# ##.#### ##..### .#####.",
            ".##.##. ####### ####### ####### .#####. ..###.. ...#...",
        ).map { it.split(' ') }

        val UNLIT = Color.parseColor("#161616")
        val RING_UNLIT = Color.parseColor("#242424")
        val BATTERY_UNLIT = Color.parseColor("#262626")
        val LABEL_GREY = Color.parseColor("#8c8c8c")
        val PERCENT_GREY = Color.parseColor("#c4c4c4")
        val AMBIENT_GREY = Color.parseColor("#6a6a6a")
        val AMBIENT_HOURS = Color.parseColor("#b4b4b4")
        val AMBIENT_MINUTES = Color.parseColor("#8a8a8a")
        val AMBIENT_COLON = Color.parseColor("#5a5a5a")
    }
}
