package com.nightwise.watchwise.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import androidx.wear.compose.material3.lazy.rememberTransformationSpec
import androidx.wear.compose.material3.lazy.transformedHeight

/** One reading of the face. [icon] is SVG path data on a 24 x 24 grid, drawn as lines. */
private class Entry(val title: String, val meaning: String, val color: Long, val icon: String)

private val ENTRIES = listOf(
    Entry(
        "Commits", "1 commit = 1,000 steps today.", 0xFF39D353,
        "M3 12H8 M16 12H21 M12 8A4 4 0 1 1 12 16A4 4 0 1 1 12 8Z",
    ),
    Entry(
        "Grid", "Fills up to your step goal. The outlined square is next. Shades are just style.",
        0xFF39D353, "M4 4H10V10H4Z M14 4H20V10H14Z M4 14H10V20H4Z M14 14H20V20H14Z",
    ),
    Entry(
        "Steps", "Steps walked today.", 0xFF1F6FEB,
        "M13 3A1.5 1.5 0 1 1 13 6A1.5 1.5 0 1 1 13 3Z M12 8L11 14L14 17L15 21 " +
            "M11 14L8 21 M12 8L8 10L7 13 M12 8L15 11L18 12",
    ),
    Entry(
        "% of goal", "How much of today's step goal is done.", 0xFFE6EDF3,
        "M6 21V4 M6 4H18L15 8L18 12H6",
    ),
    Entry(
        "km", "Distance, estimated from your steps.", 0xFFE6EDF3,
        "M12 21C7 15 6 12.5 6 9A6 6 0 0 1 18 9C18 12.5 17 15 12 21Z " +
            "M12 7A2 2 0 1 1 12 11A2 2 0 1 1 12 7Z",
    ),
    Entry(
        "Battery", "Watch battery left.", 0xFF3FB950,
        "M3 8H18V16H3Z M21 11V13 M6 11V13 M9 11V13 M12 11V13",
    ),
    Entry(
        "bpm", "Heart rate, in beats per minute.", 0xFFDA3633,
        "M12 20L5 13A4.5 4.5 0 0 1 12 7A4.5 4.5 0 0 1 19 13Z",
    ),
    Entry(
        "temp", "Temperature outside.", 0xFFBD561D,
        "M10 14V5A2 2 0 0 1 14 5V14A4 4 0 1 1 10 14Z M12 9V17",
    ),
    Entry(
        "Outer ring", "Minutes. A dot lights every 5 minutes. The red dot is seconds.", 0xFFF78166,
        "M12 3A9 9 0 1 1 3 12 M12 11A1 1 0 1 1 12 13A1 1 0 1 1 12 11Z",
    ),
    Entry(
        "-- (dashes)", "No reading available yet.", 0xFF8B949E,
        "M5 12H10 M14 12H19",
    ),
)

@Composable
fun CommitGridGuideScreen() {
    val listState = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        TransformingLazyColumn(state = listState, contentPadding = contentPadding) {
            item {
                ListHeader(modifier = Modifier.transformedHeight(this, spec)) {
                    Text("What it means")
                }
            }
            items(ENTRIES.size) { index ->
                EntryRow(ENTRIES[index], Modifier.transformedHeight(this, spec))
            }
        }
    }
}

@Composable
private fun EntryRow(entry: Entry, modifier: Modifier) {
    Row(
        modifier = modifier.fillMaxWidth().padding(start = 8.dp, end = 18.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        LineIcon(entry.icon, Color(entry.color), Modifier.size(24.dp))
        Spacer(Modifier.width(10.dp))
        Column {
            Text(entry.title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurface)
            Text(entry.meaning, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun LineIcon(data: String, color: Color, modifier: Modifier) {
    val path = remember(data) { PathParser().parsePathString(data).toPath() }
    Canvas(modifier) {
        scale(size.width / 24f, pivot = androidx.compose.ui.geometry.Offset.Zero) {
            drawPath(path, color, style = Stroke(width = 2f, cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
    }
}
