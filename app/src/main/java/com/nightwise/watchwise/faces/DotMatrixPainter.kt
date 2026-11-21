package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Shader
import androidx.core.graphics.PathParser
import java.text.NumberFormat
import java.time.ZonedDateTime
import java.util.Locale
import kotlin.math.roundToInt

/**
 * 03 · Dot Matrix — fitness.
 *
 * Interactive: dotted LED background, Doto font time with accent seconds, three stats
 * (steps, kcal, heart rate) with line icons, and a 10-block battery bar.
 *
 * Ambient (always-on, AMOLED): no dotted background and no seconds, lighter (thinner)
 * dots for the digits, everything dimmed.
 */
class DotMatrixPainter(assets: AssetManager) : FacePainter {

    private val black = Fonts.get(assets, Fonts.DOTO, 900)
    private val bold = Fonts.get(assets, Fonts.DOTO, 700)
    private val light = Fonts.get(assets, Fonts.DOTO, 500)

    private val datePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        letterSpacing = 0.08f
        textAlign = Paint.Align.CENTER
    }
    private val timePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        letterSpacing = -0.02f
        textAlign = Paint.Align.LEFT
    }
    private val secPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.LEFT }
    private val valuePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val iconPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f // in the icons' 24-unit space
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG)

    // Lucide-style 24x24 line icons from the design.
    private val stepsIcon: Path = PathParser.createPathFromPathData("M7 21l3-6 3 2v5M6 12l3-4 4 1 3 4").apply {
        addCircle(13f, 4f, 2f, Path.Direction.CW)
    }
    private val flameIcon: Path =
        PathParser.createPathFromPathData("M12 22c4 0 7-3 7-7 0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-5 5-5 8 0 4 3 7 7 7z")
    private val pulseIcon: Path = PathParser.createPathFromPathData("M3 12h4l2-5 4 10 2-5h6")

    private val numberFormat = NumberFormat.getIntegerInstance(Locale.US)

    // Dotted background: radial-gradient(#1c1c1c 1.2px, transparent 1.6px) on a 9px grid.
    private val gridTile: Bitmap = Bitmap.createBitmap(36, 36, Bitmap.Config.ARGB_8888).also { bmp ->
        val c = Canvas(bmp)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = GRID_DOT }
        c.drawCircle(18f, 18f, 1.4f * 4, p) // tile is 4x the 9px cell
    }
    private val gridShader = BitmapShader(gridTile, Shader.TileMode.REPEAT, Shader.TileMode.REPEAT)
    private val gridMatrix = Matrix()

    override fun draw(
        canvas: Canvas,
        bounds: Rect,
        time: ZonedDateTime,
        data: FaceData,
        accent: Int,
        ambient: Boolean,
    ) {
        val s = bounds.width() / DESIGN_SIZE
        val cx = bounds.exactCenterX()
        val cy = bounds.exactCenterY()
        canvas.drawColor(Color.BLACK)

        if (!ambient) {
            gridMatrix.setScale(9f * s / 36f, 9f * s / 36f)
            gridMatrix.postTranslate(bounds.left.toFloat(), bounds.top.toFloat())
            gridShader.setLocalMatrix(gridMatrix)
            gridPaint.shader = gridShader
            canvas.drawRect(bounds, gridPaint)
        }

        val grey = if (ambient) AMBIENT_GREY else LABEL_GREY
        val white = if (ambient) AMBIENT_WHITE else Color.WHITE
        val iconColor = if (ambient) AMBIENT_GREY else accent

        datePaint.typeface = bold
        datePaint.textSize = 20 * s
        datePaint.color = grey
        timePaint.typeface = if (ambient) light else black
        timePaint.textSize = 104 * s
        timePaint.color = white
        secPaint.typeface = black
        secPaint.textSize = 28 * s
        secPaint.color = accent
        valuePaint.typeface = if (ambient) light else black
        valuePaint.textSize = 22 * s
        valuePaint.color = white
        labelPaint.typeface = bold
        labelPaint.textSize = 13 * s
        labelPaint.color = grey

        // Vertical layout (column, gap 10): date, time row, stats (+6), battery (+10).
        val gap = 10 * s
        val dateH = datePaint.lineHeight()
        val timeH = 104 * 0.95f * s
        val valueH = valuePaint.lineHeight()
        val labelH = labelPaint.lineHeight()
        val statsH = 20 * s + 4 * s + valueH + 4 * s + labelH
        val batteryH = 8 * s
        val total = dateH + gap + timeH + gap + 6 * s + statsH + gap + 10 * s + batteryH
        var top = cy - total / 2

        // Date: "SUN · NOV 22"
        val date = "${time.dayShort()} · ${time.monthShort()} ${time.dayOfMonth}"
        canvas.drawText(date, cx, datePaint.baselineInBox(top, dateH), datePaint)
        top += dateH + gap

        // Time row: HH:MM plus small seconds aligned to the bottom (margin-bottom 12).
        val hm = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        val hmW = timePaint.measureText(hm)
        if (ambient) {
            canvas.drawText(hm, cx - hmW / 2, timePaint.baselineInBox(top, timeH), timePaint)
        } else {
            val ss = time.second.pad2()
            val ssW = secPaint.measureText(ss)
            val rowW = hmW + 4 * s + ssW
            val x0 = cx - rowW / 2
            canvas.drawText(hm, x0, timePaint.baselineInBox(top, timeH), timePaint)
            val ssH = secPaint.lineHeight()
            val ssTop = top + timeH - 12 * s - ssH
            canvas.drawText(ss, x0 + hmW + 4 * s, secPaint.baselineInBox(ssTop, ssH), secPaint)
        }
        top += timeH + gap + 6 * s

        // Stats grid: 3 equal columns, gap 18.
        val stats = listOf(
            Stat(stepsIcon, data.steps?.let { numberFormat.format(it) } ?: "--", "STEPS"),
            Stat(flameIcon, data.calories?.let { numberFormat.format(it) } ?: "--", "KCAL"),
            Stat(pulseIcon, data.heartRate?.toString() ?: "--", "BPM"),
        )
        val colW = stats.maxOf { maxOf(valuePaint.measureText(it.value), labelPaint.measureText(it.label), 20 * s) }
        val colGap = 18 * s
        iconPaint.color = iconColor
        stats.forEachIndexed { i, stat ->
            val colCx = cx + (i - 1) * (colW + colGap)
            var y = top
            canvas.save()
            canvas.translate(colCx - 10 * s, y)
            canvas.scale(20 * s / 24f, 20 * s / 24f)
            canvas.drawPath(stat.icon, iconPaint)
            canvas.restore()
            y += 20 * s + 4 * s
            canvas.drawText(stat.value, colCx, valuePaint.baselineInBox(y, valueH), valuePaint)
            y += valueH + 4 * s
            canvas.drawText(stat.label, colCx, labelPaint.baselineInBox(y, labelH), labelPaint)
        }
        top += statsH + gap + 10 * s

        // Battery: 10 squares of 8px, gap 4.
        val filled = (data.battery / 10f).roundToInt().coerceIn(0, 10)
        val sq = 8 * s
        val sqGap = 4 * s
        var x = cx - (10 * sq + 9 * sqGap) / 2
        for (i in 0 until 10) {
            fillPaint.color = when {
                i >= filled -> if (ambient) AMBIENT_EMPTY else EMPTY_BLOCK
                ambient -> AMBIENT_GREY
                else -> Color.WHITE
            }
            canvas.drawRect(x, top, x + sq, top + sq, fillPaint)
            x += sq + sqGap
        }
    }

    private class Stat(val icon: Path, val value: String, val label: String)

    private companion object {
        val GRID_DOT = Color.parseColor("#1c1c1c")
        val LABEL_GREY = Color.parseColor("#8c8c8c")
        val EMPTY_BLOCK = Color.parseColor("#2a2a2a")
        val AMBIENT_GREY = Color.parseColor("#6a6a6a")
        val AMBIENT_WHITE = Color.parseColor("#c8c8c8")
        val AMBIENT_EMPTY = Color.parseColor("#1a1a1a")
    }
}
