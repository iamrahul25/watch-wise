package com.nightwise.watchwise

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.MaterialTheme
import com.nightwise.watchwise.ui.AmoledColors
import com.nightwise.watchwise.ui.CommitGridGuideScreen

/**
 * What the readings on the Commit Grid face mean. Opened by tapping the info icon on the
 * face (the Launch element in tools/gen_watchfaces.py, commit_grid).
 */
class CommitGridGuideActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = AmoledColors) {
                AppScaffold { CommitGridGuideScreen() }
            }
        }
    }
}
