package com.nightwise.watchwise

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.navigation.SwipeDismissableNavHost
import androidx.wear.compose.navigation.composable
import androidx.wear.compose.navigation.rememberSwipeDismissableNavController
import com.nightwise.watchwise.faces.FacePrefs
import com.nightwise.watchwise.faces.HealthData
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.ui.AmoledColors
import com.nightwise.watchwise.ui.FaceDetailScreen
import com.nightwise.watchwise.ui.FaceListScreen

class MainActivity : ComponentActivity() {
    /** A face the phone companion asked to show (watchwise://face/<id>?accent=<name>). */
    private var requestedFace by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HealthData.start(this)
        if (savedInstanceState == null) openFrom(intent)
        setContent { WatchWiseApp(requestedFace, onRequestHandled = { requestedFace = null }) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        openFrom(intent)
    }

    /** Only selects the face and accent; setting it still takes a tap on the watch. */
    private fun openFrom(intent: Intent?) {
        val uri = intent?.data?.takeIf { it.scheme == "watchwise" && it.host == "face" } ?: return
        val face = WatchFace.byId(uri.lastPathSegment) ?: return
        val accentName = uri.getQueryParameter("accent")
        face.accents.firstOrNull { it.name == accentName }
            ?.let { FacePrefs.setAccent(this, face, it.color) }
        requestedFace = face.id
    }
}

@Composable
fun WatchWiseApp(requestedFace: String? = null, onRequestHandled: () -> Unit = {}) {
    MaterialTheme(colorScheme = AmoledColors) {
        AppScaffold {
            val nav = rememberSwipeDismissableNavController()
            LaunchedEffect(requestedFace) {
                requestedFace?.let { id ->
                    nav.navigate("face/$id") { popUpTo("faces") }
                    onRequestHandled()
                }
            }
            SwipeDismissableNavHost(navController = nav, startDestination = "faces") {
                composable("faces") {
                    FaceListScreen(onOpen = { face -> nav.navigate("face/${face.id}") })
                }
                composable("face/{id}") { entry ->
                    val face = WatchFace.byId(entry.arguments?.getString("id")) ?: WatchFace.MONO_STACK
                    FaceDetailScreen(face)
                }
            }
        }
    }
}
