package com.nightwise.watchwise.mobile.ui

import android.graphics.Rect
import android.text.format.DateFormat
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.nightwise.watchwise.faces.FaceData
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.link.WatchState
import kotlinx.coroutines.delay
import java.time.ZonedDateTime

/** The watch's readings for the previews; null = not connected, so samples are shown. */
val LocalWatchState = compositionLocalOf<WatchState?> { null }

/** Current time, ticking every [tickMs] while the app is on screen. */
@Composable
private fun rememberNow(tickMs: Long): ZonedDateTime {
    var now by remember { mutableStateOf(ZonedDateTime.now()) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(tickMs, lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                now = ZonedDateTime.now()
                delay(tickMs - System.currentTimeMillis() % tickMs)
            }
        }
    }
    return now
}

/** A live, round face drawn by the same painter the watch app uses. */
@Composable
fun FaceDial(
    face: WatchFace,
    accent: Int,
    modifier: Modifier = Modifier,
    ambient: Boolean = false,
) {
    val context = LocalContext.current
    val painter = remember(face) { face.createPainter(context.assets) }
    val now = rememberNow(if (face.animated && !ambient) 100 else 1000)
    val watch = LocalWatchState.current
    val bounds = remember { Rect() }
    Canvas(
        modifier
            .aspectRatio(1f)
            .clip(CircleShape)
            .semantics { contentDescription = "${face.title} preview" },
    ) {
        drawRect(Color.Black)
        bounds.set(0, 0, size.width.toInt(), size.height.toInt())
        val data = FaceData(
            battery = watch?.battery ?: 82,
            steps = watch?.steps?.takeIf { it > 0 } ?: 6482,
            heartRate = watch?.heartRate ?: 72,
            temperatureC = 24,
            is24Hour = DateFormat.is24HourFormat(context),
        )
        drawIntoCanvas { canvas ->
            painter.draw(canvas.nativeCanvas, bounds, now, data, accent, ambient)
        }
    }
}

/** [FaceDial] inside a drawn watch: strap, metal case, crown and a soft accent glow. */
@Composable
fun WatchMockup(
    face: WatchFace,
    accent: Int,
    modifier: Modifier = Modifier,
    ambient: Boolean = false,
    dimmed: Boolean = false,
) {
    val glow = Color(accent)
    Box(modifier.aspectRatio(0.92f), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val center = Offset(size.width / 2, size.height / 2)
            val radius = size.width * 0.37f

            if (!dimmed) {
                drawCircle(
                    Brush.radialGradient(
                        listOf(glow.copy(alpha = 0.30f), Color.Transparent),
                        center = center,
                        radius = radius * 1.65f,
                    ),
                    radius = radius * 1.65f,
                    center = center,
                )
            }

            // Strap, fading out towards the top and bottom.
            val strapWidth = radius * 1.06f
            val left = center.x - strapWidth / 2
            val strap = Color(0xFF1C1F27)
            drawRoundRect(
                Brush.verticalGradient(listOf(Color.Transparent, strap), startY = 0f, endY = center.y - radius * 0.7f),
                topLeft = Offset(left, 0f),
                size = Size(strapWidth, center.y - radius * 0.6f),
                cornerRadius = CornerRadius(radius * 0.16f),
            )
            drawRoundRect(
                Brush.verticalGradient(listOf(strap, Color.Transparent), startY = center.y + radius * 0.7f, endY = size.height),
                topLeft = Offset(left, center.y + radius * 0.6f),
                size = Size(strapWidth, size.height - center.y - radius * 0.6f),
                cornerRadius = CornerRadius(radius * 0.16f),
            )

            // Crown.
            drawRoundRect(
                Brush.verticalGradient(
                    listOf(Color(0xFF8A909C), Color(0xFF30343D), Color(0xFF6B717D)),
                    startY = center.y - radius * 0.2f,
                    endY = center.y + radius * 0.2f,
                ),
                topLeft = Offset(center.x + radius * 1.08f, center.y - radius * 0.2f),
                size = Size(radius * 0.17f, radius * 0.4f),
                cornerRadius = CornerRadius(radius * 0.06f),
            )

            // Case and bezel.
            drawCircle(
                Brush.linearGradient(
                    listOf(Color(0xFF9198A6), Color(0xFF2A2E37), Color(0xFF14161B), Color(0xFF5A606C)),
                    start = Offset(center.x - radius, center.y - radius),
                    end = Offset(center.x + radius, center.y + radius),
                ),
                radius = radius * 1.13f,
                center = center,
            )
            drawCircle(Color(0xFF050506), radius = radius * 1.07f, center = center)
            drawCircle(
                Color.White.copy(alpha = 0.07f),
                radius = radius * 1.035f,
                center = center,
                style = Stroke(radius * 0.008f),
            )
        }
        // The dial's radius is 0.37 of the width, matching the case above.
        FaceDial(face, accent, Modifier.fillMaxWidth(0.74f), ambient)
        if (dimmed) {
            Canvas(Modifier.fillMaxSize()) {
                drawCircle(Ink.copy(alpha = 0.72f), radius = size.width * 0.372f)
            }
        }
    }
}
