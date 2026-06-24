package com.fenceguard.api;

import com.fenceguard.dto.UploadResponse;
import com.fenceguard.model.SessionInfo;
import com.fenceguard.service.SessionService;
import com.fenceguard.service.UploadService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Path;

/**
 * Secure video upload endpoint.
 * Validates extension, magic bytes, enforces size limits,
 * and generates UUID filenames.
 */
@RestController
@RequestMapping("/api")
public class UploadController {

    private static final Logger log = LoggerFactory.getLogger(UploadController.class);

    private final UploadService uploadService;
    private final SessionService sessionService;

    public UploadController(UploadService uploadService, SessionService sessionService) {
        this.uploadService = uploadService;
        this.sessionService = sessionService;
    }

    @PostMapping("/upload")
    public ResponseEntity<UploadResponse> upload(@RequestParam("file") MultipartFile file) {
        try {
            Path storedPath = uploadService.storeFile(file);

            // Create a session for this upload
            SessionInfo session = sessionService.createSession(storedPath.toString());
            session.setUploadPath(storedPath.toString());

            return ResponseEntity.ok(new UploadResponse(
                    session.getSessionId(),
                    storedPath.getFileName().toString(),
                    file.getSize(),
                    "Upload successful. Use session ID to start processing."
            ));
        } catch (IllegalArgumentException e) {
            // Validation errors (bad extension, magic bytes, etc.)
            throw e; // Handled by GlobalExceptionHandler → 400
        } catch (Exception e) {
            log.error("Upload failed", e);
            throw new RuntimeException("Upload processing failed");
        }
    }
}
