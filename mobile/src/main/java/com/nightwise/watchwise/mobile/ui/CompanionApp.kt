package com.nightwise.watchwise.mobile.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.nightwise.watchwise.faces.WatchFace
import com.nightwise.watchwise.mobile.CompanionViewModel
import com.nightwise.watchwise.mobile.Link

/** Two screens: every face (home) and one face in detail. */
@Composable
fun CompanionApp(model: CompanionViewModel) {
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    val gridState = rememberLazyGridState()
    val watch = (model.link as? Link.Connected)?.watch

    CompositionLocalProvider(LocalWatchState provides watch) {
        Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
            AnimatedContent(
                targetState = openId,
                transitionSpec = {
                    val direction = if (targetState != null) 1 else -1
                    (slideInHorizontally { direction * it / 4 } + fadeIn()) togetherWith
                        (slideOutHorizontally { -direction * it / 4 } + fadeOut())
                },
                label = "screen",
                // Swiping between faces on the detail screen isn't a screen change.
                contentKey = { it != null },
            ) { id ->
                val face = WatchFace.byId(id)
                Box(Modifier.fillMaxSize().background(Ink)) {
                    if (face == null) {
                        HomeScreen(model, gridState, onOpen = { openId = it.id })
                    } else {
                        DetailScreen(model, start = face, onBack = { openId = null }, onShown = { openId = it.id })
                    }
                }
            }
        }
    }
    BackHandler(enabled = openId != null) { openId = null }
}
