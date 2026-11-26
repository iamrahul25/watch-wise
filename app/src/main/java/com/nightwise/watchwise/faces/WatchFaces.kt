package com.nightwise.watchwise.faces

import android.content.Context
import android.content.res.AssetManager
import androidx.core.content.edit

/** One accent option. [name] matches the accent flavour of the face module in watchfaces/. */
data class Accent(val name: String, val color: Int)

private fun accent(name: String, rgb: Long) = Accent(name, (0xFF000000 or rgb).toInt())

/**
 * The watch faces this app offers.
 *
 * The real watch faces are Watch Face Format packages built from watchfaces/<pushName>
 * (one APK per accent) and pushed with Watch Face Push. The in-app previews are drawn by
 * the matching [FacePainter], which follows the same design.
 */
enum class WatchFace(
    val id: String,
    /** Face module name in watchfaces/ and the asset name prefix. */
    val pushName: String,
    val title: String,
    val tagline: String,
    /** Accent options from the design; the first one is the default. */
    val accents: List<Accent>,
    /** Shows steps / heart rate. */
    val usesSensors: Boolean,
    /** Moves between seconds, so its preview redraws at 10 fps. */
    val animated: Boolean = false,
) {
    MONO_STACK(
        id = "mono_stack",
        pushName = "monostack",
        title = "Mono Stack",
        tagline = "Big type",
        accents = listOf(
            accent("red", 0xFF3B30), accent("orange", 0xFF8A00),
            accent("cyan", 0x3BD8FF), accent("white", 0xFFFFFF),
        ),
        usesSensors = false,
    ),
    DOT_MATRIX(
        id = "dot_matrix",
        pushName = "dotmatrix",
        title = "Dot Matrix",
        tagline = "Fitness",
        accents = listOf(
            accent("lime", 0xB6FF3B), accent("white", 0xFFFFFF),
            accent("cyan", 0x3BD8FF), accent("orange", 0xFF8A00),
        ),
        usesSensors = true,
    ),
    EMBER_FOREST(
        id = "ember_forest",
        pushName = "emberforest",
        title = "Ember Forest",
        tagline = "Campfire",
        // Flame colour (baked into the fire animation, so not changeable on the watch).
        accents = listOf(
            accent("orange", 0xFF8A00), accent("cyan", 0x3DD6FF),
            accent("violet", 0xB469FF), accent("green", 0x5CFF7A),
        ),
        usesSensors = true,
        animated = true,
    );

    fun createPainter(assets: AssetManager): FacePainter = when (this) {
        MONO_STACK -> MonoStackPainter(assets)
        DOT_MATRIX -> DotMatrixPainter(assets)
        EMBER_FOREST -> EmberForestPainter()
    }

    /** Package name of the pushed watch face for an accent (must start with "<app>.watchfacepush."). */
    fun packageName(accent: Accent) = "$PUSH_PREFIX${pushName}_${accent.name}"

    /** Asset base name of the bundled APK / token for an accent. */
    fun assetName(accent: Accent) = "${pushName}_${accent.name}"

    fun accentFor(color: Int) = accents.firstOrNull { it.color == color } ?: accents.first()

    companion object {
        const val PUSH_PREFIX = "com.nightwise.watchwise.watchfacepush."

        fun byId(id: String?) = entries.firstOrNull { it.id == id }

        /** Which face + accent a pushed package name belongs to. */
        fun fromPackage(packageName: String): Pair<WatchFace, Accent>? {
            if (!packageName.startsWith(PUSH_PREFIX)) return null
            val rest = packageName.removePrefix(PUSH_PREFIX)
            for (face in entries) {
                val accent = face.accents.firstOrNull { rest == "${face.pushName}_${it.name}" }
                if (accent != null) return face to accent
            }
            return null
        }
    }
}

/** Per-face settings (accent colour picked in the menu). */
object FacePrefs {
    private const val PREFS = "face_prefs"

    fun accent(context: Context, face: WatchFace): Int =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getInt("accent_${face.id}", face.accents.first().color)

    fun setAccent(context: Context, face: WatchFace, color: Int) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit {
            putInt("accent_${face.id}", color)
        }
}
