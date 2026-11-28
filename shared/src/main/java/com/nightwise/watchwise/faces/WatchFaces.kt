package com.nightwise.watchwise.faces

import android.content.Context
import android.content.res.AssetManager
import androidx.core.content.edit

/**
 * Groups for browsing the faces, in the order the apps show them. Faces within a group keep
 * their order in [WatchFace].
 */
enum class FaceCategory(val title: String, val blurb: String) {
    PIXEL_ART("Pixel Art", "Little worlds, drawn pixel by pixel"),
    DEVELOPER("Developer", "Terminals, code and commits"),
    BOLD("Bold", "Big digits you read at a glance"),
    PHOTO("Photo", "A picture behind the time"),
    ;

    /** This group's faces. */
    val faces: List<WatchFace> get() = WatchFace.entries.filter { it.category == this }
}

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
    /** Where the apps list it. */
    val category: FaceCategory,
    /** Accent options from the design; the first one is the default. */
    val accents: List<Accent>,
    /** Shows steps / heart rate. */
    val usesSensors: Boolean,
    /** Moves between seconds, so its preview redraws at 10 fps. */
    val animated: Boolean = false,
    /** The accent options are background pictures; [Accent.color] only identifies each one. */
    val hasPictures: Boolean = false,
) {
    MONO_STACK(
        id = "mono_stack",
        pushName = "monostack",
        title = "Mono Stack",
        tagline = "Big type",
        category = FaceCategory.BOLD,
        accents = listOf(
            accent("red", 0xFF3B30), accent("orange", 0xFF8A00),
            accent("cyan", 0x3BD8FF), accent("white", 0xFFFFFF),
        ),
        usesSensors = false,
    ),
    ORBIT(
        id = "orbit",
        pushName = "orbit",
        title = "Orbit",
        tagline = "Turning rings",
        category = FaceCategory.BOLD,
        accents = listOf(
            accent("orange", 0xF06A35), accent("blue", 0x4FA8FF),
            accent("lime", 0xB6F35B), accent("white", 0xF4F4F4),
        ),
        usesSensors = false,
        animated = true,
    ),
    DOT_MATRIX(
        id = "dot_matrix",
        pushName = "dotmatrix",
        title = "Dot Matrix",
        tagline = "Fitness",
        category = FaceCategory.BOLD,
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
        category = FaceCategory.PIXEL_ART,
        // Flame colour (baked into the fire animation, so not changeable on the watch).
        accents = listOf(
            accent("orange", 0xFF8A00), accent("cyan", 0x3DD6FF),
            accent("violet", 0xB469FF), accent("green", 0x5CFF7A),
        ),
        usesSensors = true,
        animated = true,
    ),
    SHELL_WINDOW(
        id = "shell_window",
        pushName = "shellwindow",
        title = "Shell Window",
        tagline = "Terminal",
        category = FaceCategory.DEVELOPER,
        // Prompt colour.
        accents = listOf(
            accent("blue", 0x4EA1FF), accent("green", 0x5FD77A),
            accent("amber", 0xFEBC2E), accent("purple", 0xC792EA),
        ),
        usesSensors = true,
    ),
    SHELL_FULL(
        id = "shell_full",
        pushName = "shellfull",
        title = "Shell Full",
        tagline = "Big terminal",
        category = FaceCategory.DEVELOPER,
        // Prompt colour.
        accents = listOf(
            accent("blue", 0x4EA1FF), accent("green", 0x5FD77A),
            accent("amber", 0xFEBC2E), accent("purple", 0xC792EA),
        ),
        usesSensors = true,
    ),
    STACK(
        id = "stack",
        pushName = "stack",
        title = "Stack",
        tagline = "At a glance",
        category = FaceCategory.BOLD,
        accents = listOf(
            accent("violet", 0xB79CFF), accent("cyan", 0x4FD1FF),
            accent("orange", 0xFF6B2C), accent("lime", 0xB6F35B),
        ),
        usesSensors = true,
    ),
    // Was called "Terminal": the id and module name stay, so saved choices and pushed faces still match.
    OUTLINE(
        id = "terminal",
        pushName = "terminal",
        title = "Outline",
        tagline = "Solid and hollow",
        category = FaceCategory.BOLD,
        accents = listOf(
            accent("orange", 0xFF8A3D), accent("cyan", 0x3DE0FF),
            accent("lime", 0xC6FF3D), accent("violet", 0xB69CFF),
        ),
        usesSensors = true,
    ),
    COMMIT_GRID(
        id = "commit_grid",
        pushName = "commitgrid",
        title = "Commit Grid",
        tagline = "Step grid",
        category = FaceCategory.DEVELOPER,
        accents = listOf(
            accent("green", 0x39D353), accent("blue", 0x58A6FF),
            accent("purple", 0xBC8CFF), accent("orange", 0xFF9E3D),
        ),
        usesSensors = true,
    ),
    SILHOUETTE(
        id = "silhouette",
        pushName = "silhouette",
        title = "Silhouette",
        tagline = "Shadow pictures",
        category = FaceCategory.PHOTO,
        // Pictures, not colours (also changeable in the watch's Customise screen).
        accents = listOf(
            accent("woman", 0xE8E8E8), accent("man", 0x9FB4C7),
            accent("tender", 0xD8CDE2), accent("close", 0xB9BDC6), accent("love", 0xE6C3CF),
        ),
        usesSensors = false,
        hasPictures = true,
    ),
    JAVA(
        id = "java",
        pushName = "java",
        title = "Java",
        tagline = "Code",
        category = FaceCategory.DEVELOPER,
        // Keyword colour.
        accents = listOf(
            accent("orange", 0xCC7832), accent("pink", 0xF06292),
            accent("cyan", 0x29C5F6), accent("lime", 0xA5D64C),
        ),
        usesSensors = true,
    ),
    SQL(
        id = "sql",
        pushName = "sql",
        title = "SQL",
        tagline = "Query",
        category = FaceCategory.DEVELOPER,
        // Keyword colour.
        accents = listOf(
            accent("cyan", 0x29B6F6), accent("violet", 0xC792EA),
            accent("orange", 0xFF8A3D), accent("pink", 0xF06292),
        ),
        usesSensors = true,
    ),
    SPACE_TERMINAL(
        id = "space_terminal",
        pushName = "spaceterminal",
        title = "Space Terminal",
        tagline = "Astronaut",
        category = FaceCategory.PIXEL_ART,
        // Colour theme of the art.
        accents = listOf(
            accent("violet", 0xB4A0FF), accent("cyan", 0x6FD8FF),
            accent("amber", 0xFFB454), accent("mint", 0x74EAB0),
        ),
        usesSensors = true,
        animated = true,
    ),
    RETRO_PIXEL(
        id = "retro_pixel",
        pushName = "retropixel",
        title = "Retro Pixel",
        tagline = "Pixel city",
        category = FaceCategory.PIXEL_ART,
        // Colour theme of the art.
        accents = listOf(
            accent("violet", 0xA66BFF), accent("blue", 0x4EA1FF),
            accent("sunset", 0xFF7A59), accent("teal", 0x3DD6B0),
        ),
        usesSensors = true,
        animated = true,
    );

    fun createPainter(assets: AssetManager): FacePainter = when (this) {
        MONO_STACK -> MonoStackPainter(assets)
        DOT_MATRIX -> DotMatrixPainter(assets)
        EMBER_FOREST -> EmberForestPainter()
        SHELL_WINDOW -> ShellWindowPainter(assets)
        SHELL_FULL -> ShellFullPainter(assets)
        STACK -> StackPainter(assets)
        OUTLINE -> TerminalPainter(assets)
        COMMIT_GRID -> CommitGridPainter(assets)
        SILHOUETTE -> SilhouettePainter(assets)
        JAVA -> JavaPainter(assets)
        SQL -> SqlPainter(assets)
        ORBIT -> OrbitPainter(assets)
        SPACE_TERMINAL -> SpaceTerminalPainter(assets)
        RETRO_PIXEL -> RetroPixelPainter(assets)
    }

    /** What the user picks between: "accent" colours or "picture"s. */
    val optionKind: String get() = if (hasPictures) "picture" else "accent"

    /** Asset path of the picture behind an option, for faces with [hasPictures]. */
    fun pictureAsset(accent: Accent) = "photos/${pushName}_${accent.name}.webp"

    /** Package name of the pushed watch face for an accent (must start with "<app>.watchfacepush."). */
    fun packageName(accent: Accent) = "$PUSH_PREFIX${pushName}_${accent.name}"

    /** Asset base name of the bundled APK / token for an accent. */
    fun assetName(accent: Accent) = "${pushName}_${accent.name}"

    fun accentFor(color: Int) = accents.firstOrNull { it.color == color } ?: accents.first()

    companion object {
        const val PUSH_PREFIX = "com.nightwise.watchwise.watchfacepush."

        fun byId(id: String?) = entries.firstOrNull { it.id == id }

        /** Every face, grouped by category: the order both apps list and page through them. */
        val browseOrder: List<WatchFace> by lazy { FaceCategory.entries.flatMap { it.faces } }

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
