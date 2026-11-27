package com.nightwise.watchwise.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Card
import androidx.wear.compose.material3.CardDefaults
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.SurfaceTransformation
import androidx.wear.compose.material3.Text
import androidx.wear.compose.material3.lazy.rememberTransformationSpec
import androidx.wear.compose.material3.lazy.transformedHeight
import androidx.compose.runtime.rememberCoroutineScope
import com.nightwise.watchwise.faces.FacePusher
import com.nightwise.watchwise.faces.InstalledFace
import com.nightwise.watchwise.faces.WatchFace
import kotlinx.coroutines.launch

@Composable
fun FaceListScreen(onOpen: (WatchFace) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var installed by remember { mutableStateOf<InstalledFace?>(null) }
    val slotVersion by FacePusher.changes.collectAsState()
    LifecycleResumeEffect(slotVersion) {
        val job = scope.launch { installed = FacePusher.installed(context) }
        onPauseOrDispose { job.cancel() }
    }

    val listState = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        TransformingLazyColumn(state = listState, contentPadding = contentPadding) {
            item {
                ListHeader(modifier = Modifier.transformedHeight(this, spec)) {
                    Text("Watch faces")
                }
            }
            items(WatchFace.entries.size) { index ->
                val face = WatchFace.entries[index]
                FaceCard(
                    face = face,
                    isActive = installed?.let { it.face == face && it.isActive } == true,
                    onClick = { onOpen(face) },
                    modifier = Modifier.transformedHeight(this, spec),
                    transformation = SurfaceTransformation(spec),
                )
            }
        }
    }
}

@Composable
private fun FaceCard(
    face: WatchFace,
    isActive: Boolean,
    onClick: () -> Unit,
    modifier: Modifier,
    transformation: androidx.wear.compose.material3.SurfaceTransformation,
) {
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        transformation = transformation,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            FacePreview(face, Modifier.size(64.dp))
            Spacer(Modifier.width(12.dp))
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(face.title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                Text(face.tagline, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (isActive) ActivePill()
            }
        }
    }
}

@Composable
fun ActivePill(modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .padding(top = 2.dp)
            .background(Color(0xFF1B2A1B), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(6.dp).background(Color(0xFF6EE26E), CircleShape))
        Spacer(Modifier.width(5.dp))
        Text(
            "Active",
            style = MaterialTheme.typography.labelSmall,
            color = Color(0xFF9BEA9B),
            textAlign = TextAlign.Center,
        )
    }
}
