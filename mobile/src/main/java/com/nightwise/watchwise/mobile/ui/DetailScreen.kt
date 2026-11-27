package com.nightwise.watchwise.mobile.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.nightwise.watchwise.faces.Accent
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.mobile.CompanionViewModel
import com.nightwise.watchwise.mobile.Link
import com.nightwise.watchwise.mobile.Notice
import com.nightwise.watchwise.mobile.Tone

private val WatchFace.about: String
    get() = when (this) {
        WatchFace.MONO_STACK -> "Giant stacked hours and minutes, ringed by a dot for every second."
        WatchFace.DOT_MATRIX -> "LED dot digits with your steps, calories and heart rate underneath."
        WatchFace.EMBER_FOREST -> "A pixel-art campfire that flickers under the pines while you walk."
        WatchFace.SHELL_WINDOW -> "Your day as a terminal window: date, status and what's next."
        WatchFace.SHELL_FULL -> "The terminal, edge to edge, with text as large as it gets."
        WatchFace.STACK -> "Tall hours over bright minutes, with date and stats at a glance."
        WatchFace.TERMINAL -> "Solid and outlined digits beside a tidy column of readings."
    }

private val WatchFace.readings: List<String>
    get() = when (this) {
        WatchFace.MONO_STACK -> listOf("Seconds ring", "Date", "Battery", "Temperature")
        WatchFace.DOT_MATRIX -> listOf("Steps", "Calories", "Heart rate", "Battery")
        WatchFace.EMBER_FOREST -> listOf("Animated", "Step goal", "Battery")
        WatchFace.SHELL_WINDOW, WatchFace.SHELL_FULL ->
            listOf("Next event", "Steps", "Heart rate", "Weather", "Battery")
        WatchFace.STACK -> listOf("Sunrise", "Next event", "Steps", "Heart rate", "Weather")
        WatchFace.TERMINAL -> listOf("Sunrise", "Next event", "Heart rate", "Weather", "Battery")
    }

/** Readable text on top of an accent colour. */
private fun onAccent(color: Color) = if (color.luminance() > 0.35f) Ink else Color.White

@Composable
fun accentButtonColors(color: Color) = ButtonDefaults.buttonColors(
    containerColor = color,
    contentColor = onAccent(color),
    disabledContainerColor = Surface2,
    disabledContentColor = TextMuted,
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DetailScreen(
    model: CompanionViewModel,
    start: WatchFace,
    onBack: () -> Unit,
    onShown: (WatchFace) -> Unit,
) {
    val faces = WatchFace.entries
    val pager = rememberPagerState(initialPage = start.ordinal) { faces.size }
    LaunchedEffect(pager.currentPage) { onShown(faces[pager.currentPage]) }
    val face = faces[pager.currentPage]
    val accent = model.accent(face)
    val tint by animateColorAsState(Color(accent.color), tween(450), label = "tint")
    var ambient by rememberSaveable { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(0f to tint.copy(alpha = 0.16f), 0.55f to Ink))
            .statusBarsPadding(),
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            BackButton(onBack)
            Spacer(Modifier.weight(1f))
            ConnectionPill(model.link)
        }
        Column(
            Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            HorizontalPager(pager, Modifier.fillMaxWidth()) { page ->
                val paged = faces[page]
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    WatchMockup(
                        paged,
                        model.accent(paged).color,
                        Modifier.widthIn(max = 320.dp).fillMaxWidth(0.76f),
                        ambient = ambient,
                    )
                }
            }
            PageDots(faces.size, pager.currentPage, tint)
            Text(face.title, style = MaterialTheme.typography.displaySmall, modifier = Modifier.padding(top = 14.dp))
            Text(
                face.about,
                style = MaterialTheme.typography.bodyLarge,
                color = TextMuted,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 32.dp, vertical = 6.dp),
            )

            SectionLabel("ACCENT · ${accent.name.uppercase()}")
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                face.accents.forEach { option ->
                    Swatch(option, selected = option == accent) { model.selectAccent(face, option) }
                }
            }

            SectionLabel("DISPLAY")
            Segmented(listOf("Normal", "Always-on"), if (ambient) 1 else 0) { ambient = it == 1 }

            SectionLabel("ON THIS FACE")
            FlowRow(
                Modifier.padding(horizontal = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                face.readings.forEach { reading ->
                    Text(
                        reading,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier
                            .background(Surface1, CircleShape)
                            .border(1.dp, Hairline, CircleShape)
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                    )
                }
            }
            Spacer(Modifier.height(24.dp))
        }
        SetBar(model, face, accent)
    }
}

/** The notice from the last attempt and the main action. */
@Composable
private fun SetBar(model: CompanionViewModel, face: WatchFace, accent: Accent) {
    val link = model.link
    val installed = (link as? Link.Connected)?.watch?.installed
    val sending = model.sending
    val sendingThis = sending?.faceId == face.id
    val isOnWatch = installed?.faceId == face.id && installed.accent == accent.name && installed.active
    val notice = model.notice?.takeIf { it.faceId == face.id }

    Column(
        Modifier.fillMaxWidth().background(Ink).navigationBarsPadding().padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        AnimatedVisibility(notice != null) {
            if (notice != null) NoticeCard(notice)
        }
        Button(
            onClick = { model.setOnWatch(face) },
            enabled = link is Link.Connected && sending == null && !isOnWatch,
            colors = accentButtonColors(Color(accent.color)),
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) {
            if (sendingThis) {
                CircularProgressIndicator(Modifier.size(20.dp), color = TextMuted, strokeWidth = 2.dp)
                Spacer(Modifier.width(12.dp))
            }
            Text(
                when {
                    sendingThis -> "Sending to watch…"
                    isOnWatch -> "✓  On your watch"
                    link !is Link.Connected -> "Connect your watch to set this face"
                    installed?.faceId == face.id && installed.accent != accent.name -> "Apply ${accent.name} on watch"
                    else -> "Set on watch"
                },
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}

@Composable
private fun NoticeCard(notice: Notice) {
    val color = when (notice.tone) {
        Tone.SUCCESS -> Mint
        Tone.ATTENTION -> Amber
        Tone.ERROR -> Coral
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 12.dp)
            .background(color.copy(alpha = 0.12f), RoundedCornerShape(18.dp))
            .border(1.dp, color.copy(alpha = 0.4f), RoundedCornerShape(18.dp))
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).background(color, CircleShape))
        Spacer(Modifier.width(12.dp))
        Text(notice.text, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun BackButton(onClick: () -> Unit) {
    Box(
        Modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(Surface1)
            .border(1.dp, Hairline, CircleShape)
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = "Back" },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(16.dp)) {
            val tip = Offset(size.width * 0.28f, size.height / 2)
            val stroke = 2.dp.toPx()
            drawLine(TextPrimary, tip, Offset(size.width * 0.68f, size.height * 0.12f), stroke, StrokeCap.Round)
            drawLine(TextPrimary, tip, Offset(size.width * 0.68f, size.height * 0.88f), stroke, StrokeCap.Round)
        }
    }
}

@Composable
private fun PageDots(count: Int, current: Int, color: Color) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(count) { index ->
            val width by animateDpAsState(if (index == current) 22.dp else 6.dp, label = "dot")
            Box(Modifier.size(width, 6.dp).background(if (index == current) color else Hairline, CircleShape))
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = TextMuted,
        modifier = Modifier.padding(top = 22.dp, bottom = 10.dp),
    )
}

@Composable
private fun Swatch(accent: Accent, selected: Boolean, onClick: () -> Unit) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(52.dp)
            .clip(CircleShape)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .border(2.dp, if (selected) TextPrimary else Color.Transparent, CircleShape)
            .semantics {
                this.selected = selected
                contentDescription = "${accent.name} accent"
            },
    ) {
        Box(Modifier.size(38.dp).background(Color(accent.color), CircleShape))
    }
}

@Composable
private fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.background(Surface1, CircleShape).border(1.dp, Hairline, CircleShape).padding(4.dp)) {
        options.forEachIndexed { index, label ->
            val on = index == selected
            Text(
                label,
                style = MaterialTheme.typography.labelMedium,
                color = if (on) Ink else TextMuted,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .width(120.dp)
                    .clip(CircleShape)
                    .background(if (on) TextPrimary else Color.Transparent)
                    .clickable(role = Role.Tab) { onSelect(index) }
                    .semantics { this.selected = on }
                    .padding(vertical = 10.dp),
            )
        }
    }
}
