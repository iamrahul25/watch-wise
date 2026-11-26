import java.io.ByteArrayOutputStream
import javax.inject.Inject

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.nightwise.watchwise"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.nightwise.watchwise"
        minSdk = 30 // Wear OS 3+ (pushing watch faces needs Wear OS 6+, checked at runtime)
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
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

// Build-time tool: Google's Watch Face Push validator CLI.
val watchFaceValidator: Configuration = configurations.create("watchFaceValidator") {
    isCanBeConsumed = false
    isCanBeResolved = true
}

dependencies {
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.wear.compose.material3)
    implementation(libs.wear.compose.foundation)
    implementation(libs.wear.compose.navigation)
    implementation(libs.wear.watchfacepush)
    watchFaceValidator(libs.watchface.validator.cli)
}

/**
 * Collects the watch face APKs built by the :watchfaces:* modules, validates each one
 * with Google's Watch Face Push validator, and writes them plus their validation tokens
 * into the app's assets:  assets/watchfaces/<face>_<accent>.apk / <face>_<accent>_token.txt
 */
abstract class BundleWatchFacesTask : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val apks: ConfigurableFileCollection

    @get:Classpath
    abstract val validatorClasspath: ConfigurableFileCollection

    @get:Input
    abstract val marketplacePackage: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @get:Inject
    abstract val exec: ExecOperations

    @TaskAction
    fun bundle() {
        val out = outputDir.get().asFile.resolve("watchfaces")
        out.deleteRecursively()
        out.mkdirs()
        val java = File(System.getProperty("java.home"), "bin/java").absolutePath
        val validatorJar = validatorClasspath.singleFile.absolutePath
        val apkFiles = apks.asFileTree.matching { include("**/*-release.apk") }.files.sortedBy { it.name }
        if (apkFiles.isEmpty()) throw GradleException("No watch face APKs found")
        apkFiles.forEach { apk ->
            // monostack-red-release.apk -> monostack_red
            val name = apk.name.removeSuffix("-release.apk").replace('-', '_')
            val stdout = ByteArrayOutputStream()
            val result = exec.exec {
                commandLine(java, "-jar", validatorJar, "--apk_path=${apk.absolutePath}",
                    "--package_name=${marketplacePackage.get()}")
                standardOutput = stdout
                errorOutput = stdout
                isIgnoreExitValue = true
            }
            val log = stdout.toString()
            // "...generated token: <base64>:<base64>". Base64 can start with '+' or '/', so match
            // the separator exactly rather than skipping non-word characters.
            val token = Regex("""(?i)token\s*[:=]\s*([A-Za-z0-9+/=:_.\-]{20,})""").find(log)?.groupValues?.get(1)
            if (result.exitValue != 0 || token == null) {
                throw GradleException("Watch face validation failed for ${apk.name}:\n$log")
            }
            apk.copyTo(out.resolve("$name.apk"), overwrite = true)
            out.resolve("${name}_token.txt").writeText(token)
            logger.lifecycle("[watchfaces] $name validated")
        }
    }
}

// Face module -> accent flavours. Keep in sync with `accents` in watchfaces/<face>/build.gradle.kts.
val watchFaceModules = mapOf(
    "monostack" to listOf("red", "orange", "cyan", "white"),
    "dotmatrix" to listOf("lime", "white", "cyan", "orange"),
    "emberforest" to listOf("orange", "cyan", "violet", "green"),
    "shellwindow" to listOf("blue", "green", "amber", "purple"),
    "shellfull" to listOf("blue", "green", "amber", "purple"),
)

val bundleWatchFaces = tasks.register<BundleWatchFacesTask>("bundleWatchFaces") {
    watchFaceModules.keys.forEach { dependsOn(":watchfaces:$it:assembleRelease") }
    // Only the release output folders: outputs/apk/<accent>/debug belongs to debug tasks
    // (e.g. from app.py option 6) that this task doesn't depend on, which Gradle rejects.
    apks.from(watchFaceModules.flatMap { (face, accents) ->
        accents.map { rootProject.file("watchfaces/$face/build/outputs/apk/$it/release") }
    })
    validatorClasspath.from(watchFaceValidator)
    marketplacePackage.set("com.nightwise.watchwise")
    outputDir.set(layout.buildDirectory.dir("generated/watchfaceAssets"))
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(bundleWatchFaces, BundleWatchFacesTask::outputDir)
    }
}
