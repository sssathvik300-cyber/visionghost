import com.google.protobuf.gradle.*

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
    id("com.google.protobuf") version "0.9.4"
}

group = "com.fenceguard"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

val grpcVersion = "1.65.1"
val protobufVersion = "4.27.2"

dependencies {
    // Spring Boot
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    // gRPC client
    implementation("io.grpc:grpc-netty-shaded:$grpcVersion")
    implementation("io.grpc:grpc-protobuf:$grpcVersion")
    implementation("io.grpc:grpc-stub:$grpcVersion")
    implementation("com.google.protobuf:protobuf-java:$protobufVersion")

    // Jakarta annotation (for gRPC generated code)
    implementation("jakarta.annotation:jakarta.annotation-api:2.1.1")
    // javax.annotation shim — gRPC codegen emits @javax.annotation.Generated
    // which Jakarta does not provide (Spring Boot 3 uses jakarta.* namespace)
    implementation("javax.annotation:javax.annotation-api:1.3.2")

    // Apache Tika for magic byte detection
    implementation("org.apache.tika:tika-core:2.9.2")

    // Rate limiting
    implementation("com.bucket4j:bucket4j-core:8.10.1")

    // Logging
    implementation("net.logstash.logback:logstash-logback-encoder:7.4")

    // Test
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }
    plugins {
        create("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }
    generateProtoTasks {
        all().forEach { task ->
            task.plugins {
                create("grpc")
            }
        }
    }
}

// Point protobuf plugin at our shared proto directory
sourceSets {
    main {
        proto {
            srcDir("../proto")
        }
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// Spring Boot's bootJar already produces the executable jar.
// Disable the plain jar so build/libs contains exactly ONE jar —
// otherwise the Docker `COPY *.jar app.jar` matches two files and fails.
tasks.named("jar") {
    enabled = false
}
