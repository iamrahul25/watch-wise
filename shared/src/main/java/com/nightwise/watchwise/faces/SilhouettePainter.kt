package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import java.time.ZonedDateTime

/**
 * Silhouette — a full-screen picture of a shadow behind frosted glass, with the day, time
 * and battery in white at the lower right. The "accent" picks the picture.
 *
 * Ambient: the picture is dropped and only the dimmed date and time stay lit.
 *
 * Mirrors the Watch Face Format version from tools/gen_watchfaces.py (silhouette).
 */
class SilhouettePainter(private val assets: AssetManager) : FacePainter {

    private val semibold = Fonts.get(assets, Fonts.SPACE_GROTESK, 600)
    private val medium = Fonts.get(assets, Fonts.SPACE_GROTESK, 500)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.RIGHT }
    private val shape = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val photo = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val pictures = HashMap<String, Bitmap>()
    private val full = RectF(0f, 0f, DESIGN_SIZE, DESIGN_SIZE)
    private val circle = Path().apply { addOval(full, Path.Direction.CW) }
    private val battery = RectF()

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
            canvas.save()
            canvas.clipPath(circle)
            canvas.drawBitmap(picture(accent), null, full, photo)
            canvas.restore()
        }

        val alpha = if (ambient) 170 else 255
        words(canvas, "${time.dayShort()} ${time.dayOfMonth}", RIGHT, 256f, 30f, semibold, alpha)
        val clock = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        words(canvas, clock, RIGHT, 336f, 96f, medium, alpha)
        if (!ambient) {
            words(canvas, "${data.battery}%", RIGHT - 40, 370f, 24f, medium, alpha)
            batterySymbol(canvas, data.battery)
        }
        canvas.restore()
    }

    private fun picture(accent: Int): Bitmap {
        val face = WatchFace.SILHOUETTE
        val asset = face.pictureAsset(face.accentFor(accent))
        return pictures.getOrPut(asset) { assets.open(asset).use { BitmapFactory.decodeStream(it) } }
    }

    /** Right-aligned text ending at [right]. */
    private fun words(
        canvas: Canvas,
        value: String,
        right: Float,
        baseline: Float,
        size: Float,
        font: Typeface,
        alpha: Int,
    ) {
        text.typeface = font
        text.textSize = size
        text.color = Color.WHITE
        text.alpha = alpha
        canvas.drawText(value, right, baseline, text)
    }

    private fun batterySymbol(canvas: Canvas, percent: Int) {
        val x = RIGHT - 30
        val y = 355f
        shape.style = Paint.Style.STROKE
        shape.strokeWidth = 2f
        battery.set(x, y, x + 26, y + 14)
        canvas.drawRoundRect(battery, 3f, 3f, shape)
        shape.style = Paint.Style.FILL
        canvas.drawRect(x + 27, y + 4, x + 30, y + 10, shape)
        canvas.drawRect(x + 3, y + 3, x + 3 + (percent / 5f).coerceIn(1f, 20f), y + 11, shape)
    }

    private companion object {
        const val RIGHT = 388f
    }
}
