pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "WatchWise"
// :app = Wear OS app, :mobile = phone companion, :shared = faces + the phone <-> watch protocol.
include(":app", ":mobile", ":shared")
// Watch Face Format faces pushed by the app (see tools/gen_watchfaces.py).
include(":watchfaces:monostack", ":watchfaces:dotmatrix", ":watchfaces:emberforest", ":watchfaces:shellwindow", ":watchfaces:shellfull", ":watchfaces:stack", ":watchfaces:terminal", ":watchfaces:commitgrid")
