package com.nightwise.watchwise.mobile.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.link.RemoteFace
import com.nightwise.watchwise.mobile.CompanionViewModel
import com.nightwise.watchwise.mobile.Link

private const val PRIVACY_POLICY_URL = "https://iamrahul25.github.io/watch-wise-pages/privacy-policy.html"

@Composable
fun HomeScreen(model: CompanionViewModel, grid: LazyGridState, onOpen: (WatchFace) -> Unit) {
    val link = model.link
    val installed = (link as? Link.Connected)?.watch?.installed
    val insets = WindowInsets.systemBars.asPaddingValues()
    FaceGrid(model, grid, installed, insets, onOpen)
    // Keeps the status bar readable while the grid scrolls underneath it.
    Box(
        Modifier
            .fillMaxWidth()
            .height(insets.calculateTopPadding() + 16.dp)
            .background(Brush.verticalGradient(0f to Ink, 0.7f to Ink.copy(alpha = 0.92f), 1f to Color.Transparent)),
    )
}

@Composable
private fun FaceGrid(
    model: CompanionViewModel,
    grid: LazyGridState,
    installed: RemoteFace?,
    insets: PaddingValues,
    onOpen: (WatchFace) -> Unit,
) {
    val link = model.link
    LazyVerticalGrid(
        columns = GridCells.Adaptive(150.dp),
        state = grid,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = 16.dp,
            end = 16.dp,
            top = insets.calculateTopPadding() + 12.dp,
            bottom = insets.calculateBottomPadding() + 24.dp,
        ),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) { Header(link) }
        item(span = { GridItemSpan(maxLineSpan) }) { HeroCard(model, onOpen) }
        item(span = { GridItemSpan(maxLineSpan) }) {
            Row(
                Modifier.fillMaxWidth().padding(top = 16.dp, start = 4.dp, end = 4.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                Text("All faces", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                Text(
                    "${WatchFace.entries.size} designs",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextMuted,
                )
            }
        }
        items(WatchFace.entries, key = { it.id }) { face ->
            FaceCard(model, face, installed, onClick = { onOpen(face) })
        }
    }
}

@Composable
private fun Header(link: Link) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("Watch Wise", style = MaterialTheme.typography.displaySmall)
            Text("Faces for your wrist", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
            val uriHandler = LocalUriHandler.current
            Text(
                "Privacy policy",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                textDecoration = TextDecoration.Underline,
                modifier = Modifier.padding(top = 4.dp).clickable { uriHandler.openUri(PRIVACY_POLICY_URL) },
            )
        }
        ConnectionPill(link)
    }
}

@Composable
fun ConnectionPill(link: Link, modifier: Modifier = Modifier) {
    val (color, label) = when (link) {
        Link.Searching -> Amber to "Searching"
        is Link.Connected -> Mint to "Connected"
        is Link.AppMissing -> Amber to "Setup"
        is Link.Offline -> Coral to "Offline"
    }
    Row(
        modifier
            .background(Surface1, CircleShape)
            .border(1.dp, Hairline, CircleShape)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).background(color, CircleShape))
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.labelMedium)
    }
}

/** What is on the wrist right now, or how to get connected. */
@Composable
private fun HeroCard(model: CompanionViewModel, onOpen: (WatchFace) -> Unit) {
    val link = model.link
    val connected = link as? Link.Connected
    val installed = connected?.watch?.installed
    val face = WatchFace.byId(installed?.faceId)
    val shown = face ?: WatchFace.MONO_STACK
    val accent = face?.accents?.firstOrNull { it.name == installed?.accent } ?: model.accent(shown)
    val tint by animateColorAsState(
        if (connected != null) Color(accent.color) else Hairline,
        tween(600),
        label = "tint",
    )

    Surface(
        shape = RoundedCornerShape(32.dp),
        color = Surface1,
        border = BorderStroke(1.dp, Hairline),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            Modifier
                .background(Brush.verticalGradient(listOf(tint.copy(alpha = 0.14f), Color.Transparent)))
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            when (link) {
                is Link.Connected -> {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                when {
                                    face == null -> "NO FACE YET"
                                    installed?.active == true -> "ON YOUR WRIST"
                                    else -> "INSTALLED, NOT SHOWING"
                                },
                                style = MaterialTheme.typography.labelSmall,
                                color = if (installed?.active == true) Mint else Amber,
                            )
                            Text(
                                link.watch.deviceName,
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextMuted,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        BatteryBadge(link.watch.battery)
                    }
                    WatchMockup(
                        shown,
                        accent.color,
                        Modifier.widthIn(max = 280.dp).fillMaxWidth(0.82f),
                        dimmed = face == null,
                    )
                    Text(face?.title ?: "Choose a face", style = MaterialTheme.typography.headlineMedium)
                    Text(
                        if (face == null) "Pick one below and send it to your watch" else
                            "${face.tagline} · ${accent.name.replaceFirstChar { it.uppercase() }}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted,
                        textAlign = TextAlign.Center,
                    )
                    if (face != null) {
                        PillButton(
                            if (installed?.active == true) "Customise" else "Finish setting up",
                            Color(accent.color),
                            Modifier.padding(top = 16.dp),
                        ) { onOpen(face) }
                    }
                    if (link.viaEmulator) {
                        Text(
                            "Linked through the debug emulator bridge",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextMuted,
                            modifier = Modifier.padding(top = 12.dp),
                        )
                    }
                }

                Link.Searching -> {
                    CircularProgressIndicator(Modifier.padding(top = 24.dp).size(40.dp), color = TextPrimary, strokeWidth = 3.dp)
                    Message("Looking for your watch", "This only takes a moment.")
                    Spacer(Modifier.height(16.dp))
                }

                is Link.AppMissing -> {
                    WatchMockup(shown, accent.color, Modifier.widthIn(max = 220.dp).fillMaxWidth(0.64f), dimmed = true)
                    Message("Add Watch Wise to your watch", "${link.watchName} is connected but doesn't have the app yet.")
                    PillButton("Install on watch", TextPrimary, Modifier.padding(top = 16.dp)) {
                        model.installOnWatch(link.nodeId)
                    }
                }

                is Link.Offline -> {
                    WatchMockup(shown, accent.color, Modifier.widthIn(max = 220.dp).fillMaxWidth(0.64f), dimmed = true)
                    Message("Watch not connected", "${link.reason}.")
                    PillButton("Try again", TextPrimary, Modifier.padding(top = 16.dp)) { model.retry() }
                }
            }
        }
    }
}

@Composable
private fun Message(title: String, body: String) {
    Text(
        title,
        style = MaterialTheme.typography.titleLarge,
        textAlign = TextAlign.Center,
        modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
    )
    Text(body, style = MaterialTheme.typography.bodyMedium, color = TextMuted, textAlign = TextAlign.Center)
}

@Composable
private fun PillButton(text: String, color: Color, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = modifier.height(48.dp),
        colors = accentButtonColors(color),
        contentPadding = PaddingValues(horizontal = 32.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
private fun BatteryBadge(percent: Int) {
    val color = if (percent <= 20) Coral else Mint
    Row(
        Modifier.background(Surface2, CircleShape).padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(22.dp).height(10.dp).border(1.dp, TextMuted, RoundedCornerShape(3.dp)).padding(2.dp)) {
            Box(
                Modifier
                    .fillMaxWidth(percent.coerceIn(0, 100) / 100f)
                    .height(6.dp)
                    .clip(RoundedCornerShape(1.dp))
                    .background(color),
            )
        }
        Spacer(Modifier.width(8.dp))
        Text("$percent%", style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun FaceCard(model: CompanionViewModel, face: WatchFace, installed: RemoteFace?, onClick: () -> Unit) {
    val onWatch = installed?.faceId == face.id
    val accent = model.accent(face)
    Surface(
        shape = RoundedCornerShape(26.dp),
        color = Surface1,
        border = BorderStroke(1.dp, if (onWatch) Color(accent.color).copy(alpha = 0.8f) else Hairline),
        modifier = Modifier.clip(RoundedCornerShape(26.dp)).clickable(onClick = onClick),
    ) {
        Column(Modifier.padding(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .background(Color(0xFF2A2F3A), CircleShape)
                    .padding(3.dp)
                    .background(Color.Black, CircleShape)
                    .padding(3.dp),
            ) {
                FaceDial(face, accent.color, Modifier.fillMaxWidth())
            }
            Text(
                face.title,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 12.dp),
            )
            Text(
                if (onWatch) (if (installed?.active == true) "● On your watch" else "● Installed") else face.tagline,
                style = MaterialTheme.typography.bodySmall,
                color = if (onWatch) Mint else TextMuted,
                maxLines = 1,
            )
            Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                face.accents.forEach { option ->
                    Box(
                        Modifier
                            .size(width = if (option == accent) 20.dp else 8.dp, height = 8.dp)
                            .background(Color(option.color), CircleShape),
                    )
                }
            }
        }
    }
}
