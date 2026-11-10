plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.ossetian.vpn"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.ossetian.vpn"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    signingConfigs {
        create("release") {
            storeFile = file("../ossetian.keystore")
            storePassword = "ossetian"
            keyAlias = "ossetian"
            keyPassword = "ossetian"
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // ядро Xray для Android (скачивается в CI, см. .github/workflows/build.yml)
    implementation(files("libs/libv2ray.aar"))
}
