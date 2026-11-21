package com.nightwise.watchwise

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.navigation.SwipeDismissableNavHost
import androidx.wear.compose.navigation.composable
import androidx.wear.compose.navigation.rememberSwipeDismissableNavController
import com.nightwise.watchwise.faces.HealthData
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.ui.AmoledColors
import com.nightwise.watchwise.ui.FaceDetailScreen
import com.nightwise.watchwise.ui.FaceListScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HealthData.start(this)
        setContent { WatchWiseApp() }
    }
}

@Composable
fun WatchWiseApp() {
    MaterialTheme(colorScheme = AmoledColors) {
        AppScaffold {
            val nav = rememberSwipeDismissableNavController()
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
