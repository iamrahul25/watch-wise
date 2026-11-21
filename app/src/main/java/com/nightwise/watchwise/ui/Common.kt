package com.nightwise.watchwise.ui

import android.graphics.Rect
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material3.ColorScheme
import com.nightwise.watchwise.faces.FacePrefs
import com.nightwise.watchwise.faces.HealthData
import com.nightwise.watchwise.faces.WatchFace
import kotlinx.coroutines.delay
import java.time.ZonedDateTime

/** Pure-black AMOLED theme: black background, near-black cards, white primary. */
val AmoledColors = ColorScheme(
    primary = Color(0xFFF2F2F2),
    primaryDim = Color(0xFFD9D9D9),
    primaryContainer = Color(0xFF262626),
    onPrimary = Color(0xFF000000),
    onPrimaryContainer = Color(0xFFF2F2F2),
    surfaceContainerLow = Color(0xFF0B0B0B),
    surfaceContainer = Color(0xFF141414),
    surfaceContainerHigh = Color(0xFF1F1F1F),
    onSurface = Color(0xFFFFFFFF),
    onSurfaceVariant = Color(0xFF9A9A9A),
    outline = Color(0xFF3A3A3A),
    outlineVariant = Color(0xFF262626),
    background = Color(0xFF000000),
    onBackground = Color(0xFFFFFFFF),
)

/** Current time, ticking on each new second. */
@Composable
fun rememberNow(): ZonedDateTime {
    var now by remember { mutableStateOf(ZonedDateTime.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1000 - System.currentTimeMillis() % 1000)
            now = ZonedDateTime.now()
        }
    }
    return now
}

/** Live, round preview of a face, drawn by the same painter as the real watch face. */
@Composable
fun FacePreview(face: WatchFace, modifier: Modifier = Modifier, accent: Int? = null) {
    val context = LocalContext.current
    val painter = remember(face) { face.createPainter(context.assets) }
    val now = rememberNow()
    val bounds = remember { Rect() }
    Canvas(
        modifier
            .aspectRatio(1f)
            .clip(CircleShape)
            .border(1.dp, Color(0xFF262626), CircleShape),
    ) {
        bounds.set(0, 0, size.width.toInt(), size.height.toInt())
        drawIntoCanvas { canvas ->
            painter.draw(
                canvas = canvas.nativeCanvas,
                bounds = bounds,
                time = now,
                data = HealthData.snapshot(context),
                accent = accent ?: FacePrefs.accent(context, face),
                ambient = false,
            )
        }
    }
}
