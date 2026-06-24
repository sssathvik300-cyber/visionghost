package com.fenceguard.dto;

/**
 * Response returned after a successful video upload.
 */
public record UploadResponse(
        String sessionId,
        String filename,
        long sizeBytes,
        String message
) {}
