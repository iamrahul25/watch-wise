// Phone companion: browse every face and set it on the watch.
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.nightwise.watchwise.mobile"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        // Must match the watch app (:app): one Play listing, and the Wearable Data Layer only
        // connects apps with the same applicationId and signing key.
        applicationId = "com.nightwise.watchwise"
        minSdk = 26
        targetSdk = 37
        // Phone = 1xxxxxx, watch = 2xxxxxx.
        versionCode = 1_000_002
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(project(":shared"))
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.play.services.wearable)
    implementation(libs.wear.remote.interactions)
    implementation(libs.kotlinx.coroutines.play.services)
    implementation(libs.androidx.concurrent.futures.ktx)
}
