package com.nightwise.watchwise.faces

import android.content.res.AssetManager
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import java.time.ZonedDateTime

/**
 * Draws one watch face onto any Canvas. Used by both the real watch face
 * (WatchFaceService renderer) and the live previews in the menu, so they always match.
 *
 * Faces are designed on a 450 x 450 px artboard (see the "AMOLED Watch Faces" design)
 * and scaled to the given bounds.
 */
interface FacePainter {
    fun draw(
        canvas: Canvas,
        bounds: Rect,
        time: ZonedDateTime,
        data: FaceData,
        accent: Int,
        ambient: Boolean,
    )
}

/** Design artboard size the faces are laid out on. */
const val DESIGN_SIZE = 450f

internal val DAYS = arrayOf("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
internal val MONTHS = arrayOf("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

/** java.time day-of-week is Mon=1..Sun=7; DAYS starts at Sunday. */
internal fun ZonedDateTime.dayShort() = DAYS[dayOfWeek.value % 7]
internal fun ZonedDateTime.monthShort() = MONTHS[monthValue - 1]

internal fun Int.pad2() = toString().padStart(2, '0')

internal fun ZonedDateTime.displayHour(is24Hour: Boolean): Int =
    if (is24Hour) hour else (hour % 12).let { if (it == 0) 12 else it }

/** Bundled variable fonts (assets/fonts), one Typeface per weight. */
object Fonts {
    const val SPACE_GROTESK = "spacegrotesk.ttf"
    const val DOTO = "doto.ttf"
    const val JETBRAINS_MONO = "jetbrainsmono_regular.ttf"
    const val JETBRAINS_MONO_EXTRABOLD = "jetbrainsmono_extrabold.ttf"

    private val cache = HashMap<String, Typeface>()

    fun get(assets: AssetManager, file: String, weight: Int): Typeface = synchronized(cache) {
        cache.getOrPut("$file@$weight") {
            Typeface.Builder(assets, "fonts/$file")
                .setFontVariationSettings("'wght' $weight")
                .build()
        }
    }

    /** A static (non-variable) font file. */
    fun static(assets: AssetManager, file: String): Typeface = synchronized(cache) {
        cache.getOrPut(file) { Typeface.createFromAsset(assets, "fonts/$file") }
    }
}

/** CSS-style "normal" line height for a paint. */
internal fun Paint.lineHeight(): Float = fontMetrics.let { it.descent - it.ascent + it.leading }

/**
 * Baseline that vertically centres a line of text in a CSS line box
 * (half-leading above and below, like a browser does).
 */
internal fun Paint.baselineInBox(top: Float, boxHeight: Float): Float {
    val fm = fontMetrics
    val ascent = -fm.ascent
    val descent = fm.descent
    return top + (boxHeight - (ascent + descent)) / 2f + ascent
}
