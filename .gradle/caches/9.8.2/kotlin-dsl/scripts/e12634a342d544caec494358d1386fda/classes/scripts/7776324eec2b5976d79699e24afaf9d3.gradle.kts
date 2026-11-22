import com.android.build.gradle.internal.api.BaseVariantOutputImpl
import org.gradle.api.tasks.Sync
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Base64
import java.util.Date
import java.util.Properties
import java.util.TimeZone

         
                                           
                           
                                      
                                      
                                            
                           
 

chaquopy {
    defaultConfig {
                                                               
                                                                                  
        val pyVersion = providers.gradleProperty("pythonVersion").orElse("3.13").get()
        version = pyVersion
                                          
        buildPython = listOf("/usr/bin/python$pyVersion")
        pip {
            install("pip")
            install("wheel")
            install("setuptools")
            install("paho-mqtt")
            install("ecdsa")
            install("requests")
        }
    }
}

apply(from = "build-logic/tasks-native.gradle.kts")
apply(from = "build-logic/tasks-plugin-dev.gradle.kts")

              
fun getGitHash(): String {
    return try {
        val process = ProcessBuilder("git", "rev-parse", "--short", "HEAD")
            .directory(rootDir)
            .start()
        process.inputStream.bufferedReader().readText().trim()
    } catch (e: Exception) {
        "unknown"
    }
}

fun getSourceFingerprint(): String {
    val sourceRoots = listOf(
        file("src/main/java"),
        file("src/main/jni/librime_jni"),
        file("src/main/python"),
        file("src/main/assets"),
        file("src/main/res"),
        file("src/main/AndroidManifest.xml"),
    )
    val sourceFiles = sourceRoots
        .flatMap { root ->
            if (root.isFile) listOf(root) else root.walkTopDown().filter { it.isFile }.toList()
        }
        .sortedBy { it.relativeTo(rootProject.projectDir).invariantSeparatorsPath }
    val digest = MessageDigest.getInstance("SHA-256")
    sourceFiles.forEach { source ->
        digest.update(source.relativeTo(rootProject.projectDir).invariantSeparatorsPath.toByteArray(Charsets.UTF_8))
        digest.update(0.toByte())
        source.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
    }
    return digest.digest().joinToString("") { it.toInt().and(0xff).toString(16).padStart(2, '0') }
}

val supportedAbis = listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64")
val buildAbis = providers.gradleProperty("buildAbis")
    .orNull
    ?.split(",")
    ?.map { it.trim() }
    ?.filter { it.isNotEmpty() }
    ?: supportedAbis
require(buildAbis.isNotEmpty() && buildAbis.all { it in supportedAbis }) {
    "buildAbis must contain only: ${supportedAbis.joinToString(", ")}"
}

val configuredAppName = providers.gradleProperty("appName").orElse("输入法").get()
val configuredChineseAppName = providers.gradleProperty("appChineseName").orElse("默认").get()
val configuredAppIconPath = providers.gradleProperty("appIconPath")
    .orElse(providers.environmentVariable("APP_ICON_PATH"))
    .orElse(layout.projectDirectory.file("src/main/res/drawable/ic_launcher_foreground.xml").asFile.absolutePath)
val configuredAppIcon = configuredAppIconPath.map { file(it).canonicalFile }
val configuredAppIconExtension = configuredAppIcon.map { it.extension.lowercase() }
val generatedAppIconResources = layout.buildDirectory.dir("generated/appIcon/res")
val generateAppIconResources = tasks.register<Sync>("generateAppIconResources") {
    val iconFile = configuredAppIcon.get()
    val iconExtension = configuredAppIconExtension.get()
    require(iconFile.isFile && iconFile.canRead() && iconFile.length() > 0) {
        "APP_ICON_PATH is missing, unreadable, or empty: $iconFile"
    }
    require(iconExtension in setOf("png", "webp", "xml")) {
        "APP_ICON_PATH must point to a PNG, WebP, or Android vector XML file: $iconFile"
    }
                                                              
                                                        
                                                           
                                                 
    val generatedDir = generatedAppIconResources.get().asFile
    inputs.file(iconFile)
    into(generatedDir)
    from(iconFile) {
        into("drawable-nodpi")
        rename { "ic_launcher_foreground.$iconExtension" }
    }
    doLast {
        if (iconExtension != "png") return@doLast
                                           
                                                                              
                                                                
        val target = generatedDir.resolve("drawable-nodpi/ic_launcher_foreground.png")
        val maxSize = 432
        val script = """
            import sys
            try:
                from PIL import Image
            except Exception:
                sys.exit(3)
            path, limit = sys.argv[1], int(sys.argv[2])
            image = Image.open(path).convert("RGBA")
            scale = limit / max(image.size)
            if scale < 1:
                size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                image.resize(size, Image.LANCZOS).save(path, "PNG")
        """.trimIndent()
        try {
            val process = ProcessBuilder(
                "python3", "-c", script, target.absolutePath, maxSize.toString()
            ).redirectErrorStream(true).start()
                               
            process.inputStream.bufferedReader().readText()
            process.waitFor()
        } catch (_: java.io.IOException) {
                                  
        }
    }
}
val configuredApplicationId = providers.gradleProperty("applicationId")
    .orElse("com.kingzcheung.xime")
    .get()
val configuredVersionCode = providers.gradleProperty("versionCode")
    .orElse("20260828")
    .get()
    .toInt()
val configuredVersionName = providers.gradleProperty("versionName")
    .orElse("版本号字符串安装界面最多显示超过会用省略号表示长度17个字符android规范合法的是1024")
    .get()
val escapedAppName = configuredAppName.replace("\\", "\\\\").replace("\"", "\\\"")
val escapedChineseAppName = configuredChineseAppName.replace("\\", "\\\\").replace("\"", "\\\"")

                                                  
                                       

         
val keystorePropertiesFile = rootProject.file("app/keystore.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(keystorePropertiesFile.inputStream())
}

android {
    namespace = "com.kingzcheung.xime"
    compileSdk = 37
                                                                              
    compileSdkMinor = 2

                                                                  
                               
    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    defaultConfig {
        applicationId = configuredApplicationId
        minSdk = 27
        targetSdk = 35
        versionCode = configuredVersionCode
        versionName = configuredVersionName

        buildConfigField("String", "APP_NAME", "\"$escapedAppName\"")
        buildConfigField("String", "APP_CHINESE_NAME", "\"$escapedChineseAppName\"")
        resValue("string", "app_name", configuredAppName)
                                               
        resValue("string", "settings_title", "${configuredAppName}设置")
                                                                 
        resValue("string", "s_zaixitongshezhizhongqiyongxima_44550", "在系统设置中启用${configuredAppName}")
        resValue("string", "s_qiehuandaoximashurufa", "切换到${configuredAppName}")
        resValue("string", "s_ximashurufa", configuredAppName)
        resValue("string", "s_qingzaixitongshezhizhongqiyong_f6c5a", "请在系统设置中启用「${configuredAppName}」")
        resValue("string", "s_ximashurufayiqiyong", "✓ ${configuredAppName}已启用")
        resValue("string", "s_qingxianzaixitongshezhizhongqi_97b2c", "请先在系统设置中启用${configuredAppName}")
        resValue("string", "s_yiqiezhunbeijiuxu_qingqiehuand_3e15e", "一切准备就绪！请切换到${configuredAppName}开始使用")


        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

                 
        ndk {
            abiFilters += buildAbis
        }

               
        buildConfigField("String", "GIT_HASH", "\"${getGitHash()}\"")
        buildConfigField("String", "SOURCE_FINGERPRINT", "\"${getSourceFingerprint()}\"")
                                                             
                                                             
                                                          
        val buildTimeWithZone = SimpleDateFormat("yyyy-MM-dd HH:mm:ss Z").format(Date())
        buildConfigField("String", "BUILD_TIME", "\"$buildTimeWithZone\"")
    }

    signingConfigs {
        getByName("debug") {
            val debugKeystore = rootProject.file("../.android/debug.keystore")
            if (debugKeystore.exists()) {
                                                          
                storeFile = debugKeystore
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
        }

        create("release") {
            if (keystorePropertiesFile.exists()) {
                                                                   
                                                            
                val storeFileProp = keystoreProperties.getProperty("storeFile")?.let { file(it) }
                storeFile = if (storeFileProp != null && storeFileProp.exists()) {
                    storeFileProp
                } else {
                    keystoreProperties.getProperty("keyBase64")?.let { keyBase64 ->
                        val ks = File(layout.buildDirectory.get().asFile, "release-keystore.jks")
                        ks.writeBytes(Base64.getDecoder().decode(keyBase64.replace("\n", "").trim()))
                        ks
                    }
                }
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
                                                        
            signingConfig = signingConfigs.getByName("debug")
        }

        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
                                                 
                                       
            if (keystorePropertiesFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }
    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
            freeCompilerArgs.add("-Xunused")
        }
    }
    buildFeatures {
        compose = true
        buildConfig = true
        aidl = true
    }

               
    externalNativeBuild {
        cmake {
            path = file("src/main/jni/CMakeLists.txt")
            version = "3.22.1"
        }
    }

           
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
    ndkVersion = "29.0.14206865"

                                                              
    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }

                                                                      
    sourceSets {
        getByName("debug") {
            res.srcDir(generatedAppIconResources.get().asFile)
        }
        getByName("release") {
            res.srcDir(generatedAppIconResources.get().asFile)
        }
        getByName("test") {
            resources.srcDirs("src/main/assets")
        }
    }
    lint {
        checkReleaseBuilds = false
        checkGeneratedSources = false
        abortOnError = false
        checkDependencies = true
    }

            
    splits {
        abi {
            isEnable = buildAbis.size > 1
            reset()
            if (buildAbis.size > 1) {
                include(*buildAbis.toTypedArray())
            }
            isUniversalApk = buildAbis.size > 1
        }
    }
}

tasks.configureEach {
    if ((name.startsWith("generate") || name.startsWith("merge") ||
            name.startsWith("process") || name.startsWith("map")) &&
        (name.contains("Debug") || name.contains("Release"))
    ) {
        dependsOn(generateAppIconResources)
    }
}

android.applicationVariants.all {
    val appName = "Xime"
    outputs.all {
        val abi = filters.find { it.filterType.toString() == "ABI" }?.identifier
            ?: buildAbis.singleOrNull()
            ?: "universal"
        (this as BaseVariantOutputImpl).outputFileName = "$appName-$versionCode-$abi.apk"
    }
}

                                                                
androidComponents {
    onVariants { variant ->
        val vc = project.findProperty("versionCode")?.toString()?.toIntOrNull()
        val vn = project.findProperty("versionName")?.toString()
        if (vc != null && vn != null) {
            variant.outputs.forEach { output ->
                output.versionCode.set(vc)
                output.versionName.set(vn)
            }
        }
    }
}
dependencies {
    implementation(project(":plugin-core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)

                                                        
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.21")
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.androidx.work.runtime.ktx)

                      
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.activity.compose)

                     
    implementation(libs.androidx.compose.material.icons.core)
    implementation(libs.androidx.compose.material.icons.extended)

                 
    implementation(libs.androidx.navigation.compose)

                
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

                 
    implementation(libs.androidx.savedstate)

                           
    implementation(libs.coil)

                                              
    implementation("com.squareup.okhttp3:okhttp:5.5.1")
                                                               
    implementation("com.squareup.okhttp3:okhttp-sse:5.5.1")
                                                     
    implementation("org.apache.commons:commons-compress:1.28.0")

                            
    implementation(libs.kaml)

                                            
    implementation(libs.androidx.autofill)

                                                 
    implementation(libs.exp4j)

                                   
    implementation("com.google.zxing:core:3.5.4")

                                               
    implementation("io.ktor:ktor-server-core:3.6.1")
    implementation("io.ktor:ktor-server-cio:3.6.1")
    implementation(libs.kotlinx.serialization.json)

                        
    implementation(libs.androidx.room3.runtime)
    ksp(libs.androidx.room3.compiler)

                                                
    implementation(platform("io.github.rosemoe:editor-bom:0.24.7"))
    implementation("io.github.rosemoe:editor")
    implementation("io.github.rosemoe:language-textmate")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")

    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.core)
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
    testImplementation("org.mockito:mockito-core:5.24.0")
    testImplementation("org.mockito.kotlin:mockito-kotlin:6.4.0")
                                                      
    testImplementation("org.json:json:20240303")

    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test:rules:1.7.0")
    androidTestImplementation("androidx.concurrent:concurrent-futures:1.2.0")
}

                                                                  
dependencies {
    constraints {
        implementation("androidx.concurrent:concurrent-futures:1.2.0") {
            because("test dependencies (espresso 3.7.0) require 1.2.0")
        }
    }
}