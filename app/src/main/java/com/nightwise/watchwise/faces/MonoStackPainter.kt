package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import java.time.ZonedDateTime
import kotlin.math.cos
import kotlin.math.sin

/**
 * 02 · Mono Stack — big stacked type.
 *
 * Interactive: white hours over grey minutes (Space Grotesk Bold 150px), date on top,
 * battery · temperature underneath, and a 60-dot seconds ring that fills as the
 * minute passes with the current second in the accent colour.
 *
 * Ambient (always-on, AMOLED): no seconds ring, digits drawn as thin outlines so
 * very few pixels are lit, everything dimmed.
 */
class MonoStackPainter(assets: AssetManager) : FacePainter {

    private val medium = Fonts.get(assets, Fonts.SPACE_GROTESK, 500)
    private val bold = Fonts.get(assets, Fonts.SPACE_GROTESK, 700)

    private val datePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = medium
        letterSpacing = 0.22f
        textAlign = Paint.Align.CENTER
    }
    private val bigPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = bold
        letterSpacing = -0.05f
        textAlign = Paint.Align.CENTER
    }
    private val statPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = medium
        letterSpacing = 0.08f
        textAlign = Paint.Align.LEFT
    }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG)

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

        // Seconds ring: 60 dots on a 208px radius.
        if (!ambient) {
            val sec = time.second
            for (i in 0 until 60) {
                val a = i * Math.PI / 30
                val current = i == sec
                val size = when {
                    current -> 9f
                    i % 5 == 0 -> 5f
                    else -> 3f
                }
                dotPaint.color = when {
                    current -> accent
                    i < sec -> Color.WHITE
                    else -> GREY_DOT
                }
                canvas.drawCircle(
                    cx + (208 * s * sin(a)).toFloat(),
                    cy - (208 * s * cos(a)).toFloat(),
                    size / 2f * s,
                    dotPaint,
                )
            }
        } else {
            // Just the 12 five-minute markers, very dim, so the shape stays recognisable.
            dotPaint.color = AMBIENT_MARKER
            for (i in 0 until 60 step 5) {
                val a = i * Math.PI / 30
                canvas.drawCircle(
                    cx + (208 * s * sin(a)).toFloat(),
                    cy - (208 * s * cos(a)).toFloat(),
                    2f * s,
                    dotPaint,
                )
            }
        }

        datePaint.textSize = 15 * s
        bigPaint.textSize = 150 * s
        statPaint.textSize = 14 * s

        val dateH = datePaint.lineHeight()
        val bigH = 150 * 0.86f * s
        val statH = statPaint.lineHeight()
        val total = dateH + 14 * s + bigH * 2 + 16 * s + statH
        var top = cy - total / 2

        // Date: "SUN 22 NOV"
        datePaint.color = if (ambient) AMBIENT_TEXT else LABEL_GREY
        val date = "${time.dayShort()} ${time.dayOfMonth} ${time.monthShort()}"
        canvas.drawText(date, cx, datePaint.baselineInBox(top, dateH), datePaint)
        top += dateH + 14 * s

        // Hours / minutes stacked.
        val hh = time.displayHour(data.is24Hour).pad2()
        val mm = time.minute.pad2()
        if (ambient) {
            bigPaint.style = Paint.Style.STROKE
            bigPaint.strokeWidth = 1.6f * s
        } else {
            bigPaint.style = Paint.Style.FILL
        }
        bigPaint.color = if (ambient) AMBIENT_HOURS else Color.WHITE
        canvas.drawText(hh, cx, bigPaint.baselineInBox(top, bigH), bigPaint)
        top += bigH
        bigPaint.color = if (ambient) AMBIENT_MINUTES else MINUTES_GREY
        canvas.drawText(mm, cx, bigPaint.baselineInBox(top, bigH), bigPaint)
        top += bigH + 16 * s

        // "84%  •  24°C"
        statPaint.color = if (ambient) AMBIENT_TEXT else LABEL_GREY
        val left = "${data.battery}%"
        val right = data.temperatureC?.let { "$it°C" } ?: "--°C"
        val gap = 14 * s
        val dot = 4 * s
        val wl = statPaint.measureText(left)
        val wr = statPaint.measureText(right)
        var x = cx - (wl + gap + dot + gap + wr) / 2
        val baseline = statPaint.baselineInBox(top, statH)
        canvas.drawText(left, x, baseline, statPaint)
        x += wl + gap
        dotPaint.color = if (ambient) AMBIENT_TEXT else accent
        canvas.drawCircle(x + dot / 2, top + statH / 2, dot / 2, dotPaint)
        x += dot + gap
        canvas.drawText(right, x, baseline, statPaint)
    }

    private companion object {
        val GREY_DOT = Color.parseColor("#2a2a2a")
        val LABEL_GREY = Color.parseColor("#8c8c8c")
        val MINUTES_GREY = Color.parseColor("#6f6f6f")
        val AMBIENT_MARKER = Color.parseColor("#333333")
        val AMBIENT_TEXT = Color.parseColor("#6a6a6a")
        val AMBIENT_HOURS = Color.parseColor("#d0d0d0")
        val AMBIENT_MINUTES = Color.parseColor("#7a7a7a")
    }
}
