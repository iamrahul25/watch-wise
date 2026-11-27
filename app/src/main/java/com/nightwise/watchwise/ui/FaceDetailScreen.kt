package com.nightwise.watchwise.ui

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.EdgeButton
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import com.nightwise.watchwise.faces.FacePrefs
import com.nightwise.watchwise.faces.FacePusher
import com.nightwise.watchwise.faces.HealthData
import com.nightwise.watchwise.faces.InstalledFace
import com.nightwise.watchwise.faces.PushResult
import com.nightwise.watchwise.faces.WatchFace
import kotlinx.coroutines.launch

@Composable
fun FaceDetailScreen(face: WatchFace) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val slotVersion by FacePusher.changes.collectAsState()
    // Re-read after a change: the phone companion can pick an accent too.
    var accent by remember(slotVersion) { mutableIntStateOf(FacePrefs.accent(context, face)) }
    var installed by remember { mutableStateOf<InstalledFace?>(null) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf<String?>(null) }
    var sensorsAllowed by remember { mutableStateOf(HealthData.hasSensorPermissions(context)) }
    var pendingSlot by remember { mutableStateOf<String?>(null) }

    fun refresh() = scope.launch { installed = FacePusher.installed(context) }

    LifecycleResumeEffect(face, slotVersion) {
        refresh()
        sensorsAllowed = HealthData.hasSensorPermissions(context)
        onPauseOrDispose { }
    }

    val selectedAccent = face.accentFor(accent)
    val isActive = installed?.let { it.face == face && it.accent == selectedAccent && it.isActive } == true

    fun showResult(result: PushResult) {
        busy = false
        status = when (result) {
            PushResult.Active -> "${face.title} is now your watch face"
            PushResult.InstalledNotActive ->
                "Installed. Long-press your watch face and pick ${face.title}."
            PushResult.Unsupported ->
                "Needs Wear OS 6 or newer. Install it with app.py, then pick it from the watch face list."
            is PushResult.Failed -> "Couldn't set the face: ${result.message}"
            is PushResult.NeedsActivatePermission -> null
        }
        status?.let { Toast.makeText(context, it, Toast.LENGTH_LONG).show() }
        refresh()
    }

    // One-time permission that lets the app make its pushed face the active one.
    val activateLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val slot = pendingSlot ?: return@rememberLauncherForActivityResult
        pendingSlot = null
        scope.launch {
            showResult(if (granted) FacePusher.activate(context, slot) else PushResult.InstalledNotActive)
        }
    }

    fun setFace() {
        busy = true
        status = null
        scope.launch {
            when (val result = FacePusher.push(context, face, selectedAccent)) {
                is PushResult.NeedsActivatePermission -> {
                    pendingSlot = result.slotId
                    activateLauncher.launch(FacePusher.ACTIVATE_PERMISSION)
                }
                else -> showResult(result)
            }
        }
    }

    // Live heart rate in the preview while this screen is open.
    if (face.usesSensors) {
        DisposableEffect(face, sensorsAllowed) {
            val owner = Any()
            HealthData.start(context)
            HealthData.setHeartRateActive(owner, context, true)
            onDispose { HealthData.setHeartRateActive(owner, context, false) }
        }
    }

    val sensorLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        sensorsAllowed = HealthData.hasSensorPermissions(context)
        HealthData.start(context)
    }

    val listState = rememberTransformingLazyColumnState()
    ScreenScaffold(
        scrollState = listState,
        edgeButton = {
            EdgeButton(
                onClick = { setFace() },
                enabled = !isActive && !busy,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            ) {
                Text(
                    when {
                        busy -> "Setting…"
                        isActive -> "Active"
                        else -> "Set face"
                    },
                )
            }
        },
    ) { contentPadding ->
        TransformingLazyColumn(state = listState, contentPadding = contentPadding) {
            item {
                FacePreview(
                    face = face,
                    accent = accent,
                    modifier = Modifier
                        .fillMaxWidth(0.78f)
                        .padding(top = 4.dp),
                )
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                    Text(face.title, style = MaterialTheme.typography.titleLarge, textAlign = TextAlign.Center)
                    Text(
                        face.tagline.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (isActive) ActivePill(Modifier.padding(top = 4.dp))
                }
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        "Accent",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 8.dp, bottom = 6.dp),
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        face.accents.forEach { option ->
                            AccentSwatch(
                                color = Color(option.color),
                                name = option.name,
                                selected = option.color == accent,
                                onClick = {
                                    accent = option.color
                                    FacePrefs.setAccent(context, face, option.color)
                                },
                            )
                        }
                    }
                }
            }
            status?.let { message ->
                item {
                    Text(
                        message,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp),
                    )
                }
            }
            if (face.usesSensors && !sensorsAllowed && HealthData.sensorsDeclared(context)) {
                item {
                    Button(
                        onClick = { sensorLauncher.launch(HealthData.sensorPermissions) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp),
                        colors = ButtonDefaults.filledTonalButtonColors(),
                        label = { Text("Allow steps & heart rate") },
                    )
                }
            }
        }
    }
}

@Composable
private fun AccentSwatch(color: Color, name: String, selected: Boolean, onClick: () -> Unit) {
    // 44dp touch target with a 28dp swatch; a white ring marks the selected colour.
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(44.dp)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .semantics {
                this.selected = selected
                contentDescription = "$name accent"
            },
    ) {
        Box(
            Modifier
                .size(38.dp)
                .border(2.dp, if (selected) Color.White else Color.Transparent, CircleShape),
        )
        Box(
            Modifier
                .size(28.dp)
                .background(color, CircleShape),
        )
    }
}
