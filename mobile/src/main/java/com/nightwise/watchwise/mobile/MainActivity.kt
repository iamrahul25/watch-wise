package com.nightwise.watchwise.mobile

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.nightwise.watchwise.mobile.ui.CompanionApp
import com.nightwise.watchwise.mobile.ui.WatchWiseTheme

class MainActivity : ComponentActivity() {
    private val model: CompanionViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        // Always dark, so always light system bar icons.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent {
            val lifecycle = LocalLifecycleOwner.current.lifecycle
            LaunchedEffect(lifecycle) {
                lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { model.watchStatus() }
            }
            WatchWiseTheme { CompanionApp(model) }
        }
    }
}
