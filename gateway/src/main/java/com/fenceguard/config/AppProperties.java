package com.fenceguard.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.util.Set;

/**
 * Centralized application configuration bound from environment variables / application.yml.
 * All secrets come from environment — never hardcoded.
 */
@ConfigurationProperties(prefix = "fenceguard")
public record AppProperties(
        @NotBlank String apiKey,
        @NotBlank String internalToken,
        String host,
        @Positive int port,
        GrpcConfig grpc,
        UploadConfig upload
) {
    public AppProperties {
        if (host == null) host = "127.0.0.1";
        if (port == 0) port = 8080;
        if (grpc == null) grpc = new GrpcConfig("127.0.0.1", 50051);
        if (upload == null) upload = new UploadConfig(200, Set.of(".mp4", ".mov", ".avi", ".mkv"));
    }

    public record GrpcConfig(
            String host,
            @Positive int port
    ) {
        public GrpcConfig {
            if (host == null) host = "127.0.0.1";
            if (port == 0) port = 50051;
        }
    }

    public record UploadConfig(
            @Positive int maxSizeMb,
            Set<String> allowedExtensions
    ) {
        public UploadConfig {
            if (maxSizeMb == 0) maxSizeMb = 200;
            if (allowedExtensions == null)
                allowedExtensions = Set.of(".mp4", ".mov", ".avi", ".mkv");
        }
    }
}
