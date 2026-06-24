# Build stage
FROM gradle:8.5-jdk17 AS builder
WORKDIR /app

# Copy necessary files for build
COPY gateway/build.gradle.kts gateway/settings.gradle.kts /app/gateway/
COPY proto /app/proto
COPY gateway/src /app/gateway/src

# Run gradle build excluding tests
WORKDIR /app/gateway
RUN gradle build -x test

# Run stage
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app

# Create a non-root user for security
RUN useradd -m -s /bin/bash fenceguard
RUN mkdir -p /app/uploads && chown fenceguard:fenceguard /app/uploads

# Copy the built jar
COPY --from=builder /app/gateway/build/libs/*.jar app.jar

# Ensure the user has permissions to the jar
RUN chown fenceguard:fenceguard app.jar

# Run as non-root user
USER fenceguard

# Start the application
ENTRYPOINT ["java", "-jar", "app.jar"]
