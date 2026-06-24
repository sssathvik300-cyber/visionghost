package com.fenceguard.service;

import com.fenceguard.config.AppProperties;
import org.apache.tika.Tika;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Secure file upload service.
 * - Extension allowlist validation
 * - Apache Tika magic byte verification (content type, not just extension)
 * - UUID filename generation (never uses client-supplied name)
 * - Path traversal protection via normalize + startsWith check
 */
@Service
public class UploadService {

    private static final Logger log = LoggerFactory.getLogger(UploadService.class);

    private final AppProperties appProperties;
    private final Path uploadDir;
    private final Tika tika = new Tika();

    /**
     * Maps file extensions to expected MIME type prefixes detected by Tika.
     */
    private static final Map<String, Set<String>> EXTENSION_MIME_MAP = Map.of(
            ".mp4", Set.of("video/mp4", "application/mp4"),
            ".mov", Set.of("video/quicktime"),
            ".avi", Set.of("video/avi", "video/x-msvideo", "video/vnd.avi"),
            ".mkv", Set.of("video/x-matroska")
    );

    public UploadService(AppProperties appProperties) {
        this.appProperties = appProperties;
        this.uploadDir = Path.of("uploads").toAbsolutePath().normalize();
        try {
            Files.createDirectories(uploadDir);
        } catch (IOException e) {
            throw new RuntimeException("Failed to create upload directory", e);
        }
    }

    /**
     * Validate and store an uploaded file. Returns the stored path.
     *
     * @throws IllegalArgumentException if validation fails
     */
    public Path storeFile(MultipartFile file) throws IOException {
        // 1. Check not empty
        if (file.isEmpty()) {
            throw new IllegalArgumentException("Upload file is empty");
        }

        // 2. Extract and validate extension
        String originalFilename = file.getOriginalFilename();
        String extension = extractExtension(originalFilename);

        if (!appProperties.upload().allowedExtensions().contains(extension.toLowerCase())) {
            throw new IllegalArgumentException(
                    "File type not allowed. Accepted: " +
                    appProperties.upload().allowedExtensions());
        }

        // 3. Verify content type with Apache Tika (magic bytes)
        String detectedType;
        try (InputStream is = file.getInputStream()) {
            detectedType = tika.detect(is, originalFilename);
        }

        Set<String> expectedTypes = EXTENSION_MIME_MAP.get(extension.toLowerCase());
        if (expectedTypes == null || !matchesMimeType(detectedType, expectedTypes)) {
            log.warn("Magic byte mismatch: extension={}, detected={}, file={}",
                    extension, detectedType, originalFilename);
            throw new IllegalArgumentException(
                    "File content does not match extension. Detected: " + detectedType);
        }

        // 4. Generate safe UUID filename — NEVER use client-supplied name
        String safeFilename = UUID.randomUUID() + extension.toLowerCase();
        Path targetPath = uploadDir.resolve(safeFilename).normalize();

        // 5. Path traversal protection
        if (!targetPath.startsWith(uploadDir)) {
            log.error("Path traversal attempt detected: original={}, resolved={}",
                    originalFilename, targetPath);
            throw new IllegalArgumentException("Invalid file path");
        }

        // 6. Store file
        try (InputStream is = file.getInputStream()) {
            Files.copy(is, targetPath, StandardCopyOption.REPLACE_EXISTING);
        }

        log.info("File stored: {} -> {} ({} bytes)", originalFilename, safeFilename, file.getSize());
        return targetPath;
    }

    /**
     * Delete a previously uploaded file.
     */
    public void deleteFile(Path path) {
        try {
            if (path != null && Files.exists(path)) {
                Files.delete(path);
                log.info("Deleted upload: {}", path.getFileName());
            }
        } catch (IOException e) {
            log.warn("Failed to delete upload: {}", path, e);
        }
    }

    private String extractExtension(String filename) {
        if (filename == null || !filename.contains(".")) {
            throw new IllegalArgumentException("File must have an extension");
        }
        // Use only the last extension to prevent double-extension attacks
        return filename.substring(filename.lastIndexOf('.')).toLowerCase();
    }

    private boolean matchesMimeType(String detected, Set<String> expected) {
        if (detected == null) return false;
        String lower = detected.toLowerCase();
        return expected.stream().anyMatch(lower::startsWith);
    }
}
