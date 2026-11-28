package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import org.json.JSONObject
import java.time.ZonedDateTime
import kotlin.math.floor

/*
 * Previews of the two pixel-art faces, Space Terminal and Retro Pixel. The art, icons and
 * each theme's text colours are the ones the watch uses: tools/gen_watchfaces.py writes them
 * to assets/pixel. The positions below are the same as in the generator (SP_* and RP_*),
 * measured from the design mockup. The moving pixels are the same loop of frames the watch
 * plays, from tools/pixel_motion.py.
 */

/** Shared drawing for the pixel faces, in design coordinates. */
abstract class PixelPainter(private val assets: AssetManager, private val face: WatchFace) : FacePainter {

    protected val bold: Typeface = Fonts.static(assets, Fonts.JETBRAINS_MONO_EXTRABOLD)
    protected val regular: Typeface = Fonts.static(assets, Fonts.JETBRAINS_MONO)

    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fill = Paint()
    private val image = Paint() // no filtering: keeps the pixels sharp
    private val images = HashMap<String, Bitmap>()
    private val box = RectF(0f, 0f, DESIGN_SIZE, DESIGN_SIZE)
    private var motionFrame = -1
    private var motionBitmap: Bitmap? = null

    /** Text colours per theme: {"violet": {"time": "#rrggbb", ...}, ...}. */
    private val colours: JSONObject by lazy {
        JSONObject(assets.open("pixel/${face.pushName}.json").bufferedReader().use { it.readText() })
    }

    final override fun draw(
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
        draw(canvas, time, data, face.accentFor(accent).name, ambient)
        canvas.restore()
    }

    protected abstract fun draw(canvas: Canvas, time: ZonedDateTime, data: FaceData, theme: String, ambient: Boolean)

    protected fun colour(theme: String, key: String): Int =
        Color.parseColor(colours.getJSONObject(theme).getString(key))

    /** Draws assets/pixel/<face>_[name].png with its top left at ([x], [y]). */
    protected fun picture(canvas: Canvas, name: String, x: Float = 0f, y: Float = 0f, alpha: Int = 255) {
        val file = "pixel/${face.pushName}_$name.png"
        val bitmap = images.getOrPut(file) { assets.open(file).use { BitmapFactory.decodeStream(it) } }
        image.alpha = alpha
        canvas.drawBitmap(bitmap, x, y, image)
        image.alpha = 255
    }

    /** The frame of the motion loop (pixel_motion.py: 80 frames at 10 fps) due at [time]. */
    protected fun motion(canvas: Canvas, time: ZonedDateTime) {
        val frame = (time.second * 10 + time.nano / 100_000_000) % 80
        // Only the current frame is kept: all 80 would take far more memory than decoding costs.
        if (frame != motionFrame) {
            val file = "pixel/${face.pushName}_motion_${frame.pad2()}.png"
            motionBitmap = assets.open(file).use { BitmapFactory.decodeStream(it) }
            motionFrame = frame
        }
        val bitmap = motionBitmap ?: return
        // The frames are on the art grid, half the design size.
        canvas.drawBitmap(bitmap, null, box, image)
    }

    protected fun block(canvas: Canvas, x: Float, y: Float, width: Float, height: Float, color: Int) {
        fill.color = color
        canvas.drawRect(x, y, x + width, y + height, fill)
    }

    /** Text starting at [x] (or centred on it). */
    protected fun words(
        canvas: Canvas,
        value: String,
        x: Float,
        baseline: Float,
        size: Float,
        color: Int,
        font: Typeface = regular,
        alpha: Int = 255,
        centre: Boolean = false,
    ) {
        text.typeface = font
        text.textSize = size
        text.color = color
        text.alpha = alpha
        text.textAlign = if (centre) Paint.Align.CENTER else Paint.Align.LEFT
        canvas.drawText(value, x, baseline, text)
    }

    /** hh:mm, one digit at each of [digits] and the colon at [colon]. */
    protected fun clock(
        canvas: Canvas,
        time: ZonedDateTime,
        data: FaceData,
        digits: FloatArray,
        colon: Float,
        baseline: Float,
        size: Float,
        color: Int,
        alpha: Int,
    ) {
        val value = time.displayHour(data.is24Hour).pad2() + time.minute.pad2()
        for (k in 0..3) words(canvas, value[k].toString(), digits[k], baseline, size, color, bold, alpha, centre = true)
        words(canvas, ":", colon, baseline, size, color, bold, alpha, centre = true)
    }

    /** "Thu, 26 Nov". */
    protected fun date(time: ZonedDateTime): String {
        val day = time.dayShort().lowercase().replaceFirstChar { it.uppercase() }
        val month = time.monthShort().lowercase().replaceFirstChar { it.uppercase() }
        return "$day, ${time.dayOfMonth} $month"
    }

    protected fun steps(steps: Int?) = when {
        steps == null -> "--"
        steps < 1000 -> "$steps"
        else -> "${steps / 1000}.${steps / 100 % 10}k"
    }
}

/**
 * Space Terminal — a pixel astronaut on a moon beside a terminal-style column: time, date,
 * weather, battery, heart rate and steps. The accent picks the art's colour theme.
 *
 * Ambient: only the dimmed time, date and battery stay lit.
 */
class SpaceTerminalPainter(assets: AssetManager) : PixelPainter(assets, WatchFace.SPACE_TERMINAL) {

    override fun draw(canvas: Canvas, time: ZonedDateTime, data: FaceData, theme: String, ambient: Boolean) {
        if (!ambient) {
            picture(canvas, "${theme}_scene")
            motion(canvas, time)
        }
        clock(canvas, time, data, DIGITS, 306.2f, 147f, 60f, colour(theme, "time"), if (ambient) 220 else 255)
        words(canvas, date(time), 242.9f, 181.5f, 20.5f, colour(theme, "date"), alpha = if (ambient) 170 else 255)

        val text = colour(theme, "text")
        picture(canvas, "icon_battery", 246f, 260f)
        words(canvas, "${data.battery}%", TEXT_X, 285f, 21f, text, alpha = if (ambient) 140 else 255)
        if (ambient) return

        val rule = colour(theme, "rule")
        for (k in 0 until 13) block(canvas, 238.1f + k * 12.73f, 203.6f, 9.6f, 2f, rule)
        picture(canvas, "icon_moon", 246f, 220f)
        words(canvas, data.temperatureC?.let { "$it°C" } ?: "--°", TEXT_X, 245f, 21f, text)
        picture(canvas, "icon_heart", 246f, 300f)
        words(canvas, "${data.heartRate ?: "--"} bpm", TEXT_X, 325f, 21f, text)
        picture(canvas, "icon_shoe", 246f, 340f)
        words(canvas, steps(data.steps), TEXT_X, 365f, 21f, text)
    }

    private companion object {
        const val TEXT_X = 289f
        val DIGITS = floatArrayOf(249.5f, 282.7f, 330.8f, 363.4f)
    }
}

/**
 * Retro Pixel — a kid and a cat on a rooftop watching the city under the moon, with the
 * time and date above and a panel of readings. The accent picks the colour of the night.
 *
 * Ambient: only the dimmed time (without seconds) and date stay lit.
 */
class RetroPixelPainter(assets: AssetManager) : PixelPainter(assets, WatchFace.RETRO_PIXEL) {

    override fun draw(canvas: Canvas, time: ZonedDateTime, data: FaceData, theme: String, ambient: Boolean) {
        if (!ambient) {
            picture(canvas, "${theme}_scene")
            if (time.second % 10 >= 6) picture(canvas, "${theme}_lights")
            motion(canvas, time)
            // Two clouds drifting across, as RP_CLOUDS in the generator.
            val seconds = time.second + time.nano / 1e9f
            cloud(canvas, theme, seconds, start = 0, down = 0, alpha = 255)
            cloud(canvas, theme, seconds, start = 150, down = 21, alpha = 150)
        }
        clock(canvas, time, data, DIGITS, 251.7f, 145f, 52f, colour(theme, "time"), if (ambient) 220 else 255)
        words(canvas, date(time), 216.1f, 180.5f, 21f, colour(theme, "date"), alpha = if (ambient) 170 else 255)
        if (ambient) return

        val seconds = colour(theme, "seconds")
        val ss = time.second.pad2()
        words(canvas, ":", 332.4f, 145f, 52f, seconds, centre = true)
        words(canvas, ss.substring(0, 1), 354.1f, 145f, 52f, seconds, centre = true)
        words(canvas, ss.substring(1), 381.6f, 145f, 52f, seconds, centre = true)

        val text = colour(theme, "text")
        picture(canvas, "icon_battery", 324f, 222f)
        words(canvas, "${data.battery}%", TEXT_X, 246.5f, 21f, text)
        picture(canvas, "icon_heart", 324f, 264f)
        words(canvas, "${data.heartRate ?: "--"}", TEXT_X, 287.5f, 21f, text)
        picture(canvas, "icon_shoe", 324f, 304f)
        words(canvas, steps(data.steps), TEXT_X, 329f, 21f, text)
    }

    /** A cloud picture (72 art px wide) crossing the screen once a minute. */
    private fun cloud(canvas: Canvas, theme: String, seconds: Float, start: Int, down: Int, alpha: Int) {
        val travel = seconds * (225 + 72) / 60f + start + 72
        val x = floor(travel % (225 + 72) - 72)
        picture(canvas, "${theme}_cloud", x * 2, (50 + down) * 2f, alpha)
    }

    private companion object {
        const val TEXT_X = 369f
        val DIGITS = floatArrayOf(193.8f, 225.3f, 280.3f, 310.0f)
    }
}
