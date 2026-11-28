package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import java.time.ZonedDateTime

/**
 * Base of the "code" faces: seven lines of bold monospace text, each coloured span placed by
 * its row and column. The accent is the keyword colour.
 *
 * Mirrors the Watch Face Format versions from tools/gen_watchfaces.py (java_face, sql_face).
 */
abstract class CodePainter(
    assets: AssetManager,
    private val left: Float,
    private val size: Float = SIZE,
    private val line: Float = LINE,
) : FacePainter {

    /** Width of one monospace column. */
    protected val column = 0.6f * size

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Fonts.static(assets, Fonts.JETBRAINS_MONO_EXTRABOLD)
        // Keeps "//" and "---" as separate characters.
        fontFeatureSettings = "'liga' 0, 'calt' 0"
    }

    private var canvas: Canvas? = null
    private var ambient = false

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
        this.canvas = canvas
        this.ambient = ambient
        code(time, data, accent)
        this.canvas = null
        canvas.restore()
    }

    protected abstract fun code(time: ZonedDateTime, data: FaceData, accent: Int)

    /** Text starting at column [col] of line [row]. [isTime] stays brighter in ambient mode. */
    protected fun span(
        row: Int,
        col: Float,
        value: String,
        color: Int,
        textSize: Float = size,
        isTime: Boolean = false,
    ) {
        text.textSize = size
        val metrics = text.fontMetrics
        // All sizes on a line share the body text's baseline.
        val top = (DESIGN_SIZE - 7 * line) / 2
        val baseline = top + row * line + (line - (metrics.descent - metrics.ascent)) / 2 - metrics.ascent
        text.textSize = textSize
        text.color = color
        text.alpha = if (!ambient) 255 else if (isTime) 230 else 140
        canvas?.drawText(value, left + col * column, baseline, text)
    }

    protected fun span(row: Int, col: Int, value: String, color: Int, isTime: Boolean = false) =
        span(row, col.toFloat(), value, color, isTime = isTime)

    protected companion object {
        const val SIZE = 32f
        const val LINE = 42f
    }
}

/** Java — the time, day, steps and heart rate as the fields of a class, battery in a comment. */
class JavaPainter(assets: AssetManager) : CodePainter(assets, left = 72f, size = 34f, line = 46f) {

    override fun code(time: ZonedDateTime, data: FaceData, accent: Int) {
        val nameColumn = 6f
        val nameColumns = 5 * 0.6f * CLASS_SIZE / column
        span(0, 0, "class", accent)
        span(0, nameColumn, "Watch", CLASS, CLASS_SIZE)
        span(0, nameColumn + nameColumns + 0.6f, "{", TEXT)

        field(1, "hh", time.displayHour(data.is24Hour).pad2(), accent)
        field(2, "mm", time.minute.pad2(), accent)

        span(3, 1, "String", TEXT)
        span(3, 8, "day", FIELD)
        span(3, 11, "=", TEXT)
        span(3, 12, "\"${time.dayShort()}\"", STRING)
        span(3, 17, ";", TEXT)

        span(4, 1, "int", accent)
        span(4, 5, "steps", FIELD)
        span(4, 10, "=", TEXT)
        number(4, data.steps?.toString() ?: "--")

        span(5, 1, "int", accent)
        span(5, 5, "bpm", FIELD)
        span(5, 9, "=", TEXT)
        number(5, data.heartRate?.toString() ?: "--")

        span(6, 0, "}", TEXT)
        span(6, 2, "// ${data.battery}%", COMMENT)
    }

    /** "int hh = 20;" */
    private fun field(row: Int, name: String, value: String, accent: Int) {
        span(row, 1, "int", accent)
        span(row, 5, name, FIELD)
        span(row, 8, "=", TEXT)
        span(row, 10, value, NUMBER, isTime = true)
        span(row, 12, ";", TEXT)
    }

    /** A number in column 11 followed by its semicolon. */
    private fun number(row: Int, value: String) {
        span(row, 11, value, NUMBER)
        span(row, 11 + value.length, ";", TEXT)
    }

    private companion object {
        const val CLASS_SIZE = 41f

        val TEXT = Color.parseColor("#a9b7c6")
        val FIELD = Color.parseColor("#9876aa")
        val NUMBER = Color.parseColor("#6897bb")
        val STRING = Color.parseColor("#6a8759")
        val COMMENT = Color.parseColor("#808080")
        val CLASS = Color.parseColor("#ffc66d")
    }
}

/** SQL — a query for the watch, with the time and heart rate in its result table. */
class SqlPainter(assets: AssetManager) :
    CodePainter(assets, (DESIGN_SIZE - 17 * 0.6f * 32f) / 2) {

    override fun code(time: ZonedDateTime, data: FaceData, accent: Int) {
        span(0, 0, "SELECT", accent)
        span(0, 7, "time, bpm", TEXT)
        span(1, 0, "FROM", accent)
        span(1, 5, "watch", TEXT)
        span(2, 0, "WHERE", accent)
        span(2, 6, "day=", TEXT)
        span(2, 10, "'${time.dayShort()}'", STRING)
        span(2, 15, ";", TEXT)

        span(3, 0, BORDER, GREEN)
        for (col in intArrayOf(0, 8, 14)) span(4, col, "|", GREEN)
        val clock = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        span(4, 2, clock, Color.WHITE, isTime = true)
        val bpm = data.heartRate?.toString() ?: "--"
        span(4, 13 - bpm.length, bpm, Color.WHITE) // right-aligned in its cell
        span(5, 0, BORDER, GREEN)

        // Five-digit counts start half a column further left, to stay inside the round screen.
        val steps = data.steps?.toString() ?: "--"
        span(6, if (steps.length < 5) 0f else -0.5f, "1 row, $steps steps", GREEN)
    }

    private companion object {
        const val BORDER = "+-------+-----+"

        val TEXT = Color.parseColor("#d4d4d4")
        val STRING = Color.parseColor("#f0a732")
        val GREEN = Color.parseColor("#7cb342")
    }
}
