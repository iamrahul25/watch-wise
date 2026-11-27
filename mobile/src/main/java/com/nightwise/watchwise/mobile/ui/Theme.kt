package com.nightwise.watchwise.mobile.ui

import android.content.res.AssetManager
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF07080B)
val Surface1 = Color(0xFF101218)
val Surface2 = Color(0xFF181B23)
val Hairline = Color(0xFF262B36)
val TextPrimary = Color(0xFFF4F6FA)
val TextMuted = Color(0xFF8D95A7)
val Mint = Color(0xFF5EE6A8)
val Amber = Color(0xFFFFC257)
val Coral = Color(0xFFFF7066)

private val Colors = darkColorScheme(
    primary = TextPrimary,
    onPrimary = Ink,
    background = Ink,
    onBackground = TextPrimary,
    surface = Surface1,
    onSurface = TextPrimary,
    surfaceVariant = Surface2,
    onSurfaceVariant = TextMuted,
    outline = Hairline,
)

/** Space Grotesk, the variable font the faces use (shared module assets). */
private fun spaceGrotesk(assets: AssetManager) = FontFamily(
    listOf(FontWeight.Normal, FontWeight.Medium, FontWeight.SemiBold, FontWeight.Bold).map { weight ->
        Font(
            path = "fonts/spacegrotesk.ttf",
            assetManager = assets,
            weight = weight,
            variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)),
        )
    },
)

@Composable
fun WatchWiseTheme(content: @Composable () -> Unit) {
    val assets = LocalContext.current.assets
    val typography = remember(assets) {
        val family = spaceGrotesk(assets)
        val base = Typography()
        Typography(
            displaySmall = base.displaySmall.copy(fontFamily = family, fontWeight = FontWeight.Bold, fontSize = 34.sp, letterSpacing = (-0.5).sp),
            headlineMedium = base.headlineMedium.copy(fontFamily = family, fontWeight = FontWeight.Bold),
            titleLarge = base.titleLarge.copy(fontFamily = family, fontWeight = FontWeight.Bold),
            titleMedium = base.titleMedium.copy(fontFamily = family, fontWeight = FontWeight.SemiBold),
            bodyLarge = base.bodyLarge.copy(fontFamily = family),
            bodyMedium = base.bodyMedium.copy(fontFamily = family),
            bodySmall = base.bodySmall.copy(fontFamily = family),
            labelLarge = base.labelLarge.copy(fontFamily = family, fontWeight = FontWeight.SemiBold, fontSize = 15.sp),
            labelMedium = base.labelMedium.copy(fontFamily = family),
            labelSmall = base.labelSmall.copy(fontFamily = family, fontWeight = FontWeight.SemiBold, letterSpacing = 1.2.sp),
        )
    }
    MaterialTheme(colorScheme = Colors, typography = typography, content = content)
}
