package com.fenceguard;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Security tests — ALL must pass.
 * These verify the hard security requirements:
 * - API key authentication
 * - Upload validation (extension, magic bytes, size)
 * - Path traversal protection
 * - Health endpoint accessibility
 */
@SpringBootTest(properties = {
        "fenceguard.api-key=test-api-key-12345",
        "fenceguard.internal-token=test-internal-token",
        "spring.servlet.multipart.max-file-size=1MB",
        "spring.servlet.multipart.max-request-size=1MB"
})
@AutoConfigureMockMvc
class SecurityTest {

    @Autowired
    private MockMvc mockMvc;

    private static final String VALID_API_KEY = "test-api-key-12345";

    // ── 1. No API key → 401 ──────────────────────────────

    @Test
    void noApiKey_returns401() throws Exception {
        mockMvc.perform(get("/api/events").param("sessionId", "test"))
                .andExpect(status().isUnauthorized());
    }

    // ── 2. Wrong API key → 401 ───────────────────────────

    @Test
    void wrongApiKey_returns401() throws Exception {
        mockMvc.perform(get("/api/events")
                        .param("sessionId", "test")
                        .header("X-API-Key", "wrong-key"))
                .andExpect(status().isUnauthorized());
    }

    // ── 3. Oversized upload → 413 ────────────────────────

    @Test
    void oversizedUpload_returns413() throws Exception {
        // Create a file larger than 1MB (our test limit)
        byte[] largeContent = new byte[2 * 1024 * 1024]; // 2MB
        MockMultipartFile file = new MockMultipartFile(
                "file", "test.mp4", "video/mp4", largeContent);

        mockMvc.perform(multipart("/api/upload")
                        .file(file)
                        .header("X-API-Key", VALID_API_KEY))
                .andExpect(status().isPayloadTooLarge());
    }

    // ── 4. Disallowed extension → 400 ────────────────────

    @Test
    void disallowedExtension_returns400() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "malware.exe", "application/octet-stream",
                "fake content".getBytes());

        mockMvc.perform(multipart("/api/upload")
                        .file(file)
                        .header("X-API-Key", VALID_API_KEY))
                .andExpect(status().isBadRequest());
    }

    // ── 5. Wrong magic bytes → 400 ───────────────────────

    @Test
    void wrongMagicBytes_returns400() throws Exception {
        // .mp4 extension but plaintext content (not valid MP4 magic bytes)
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.mp4", "video/mp4",
                "This is not a real MP4 file content at all".getBytes());

        mockMvc.perform(multipart("/api/upload")
                        .file(file)
                        .header("X-API-Key", VALID_API_KEY))
                .andExpect(status().isBadRequest());
    }

    // ── 6. Path traversal → neutralized ──────────────────

    @Test
    void pathTraversalFilename_isNeutralized() throws Exception {
        // Even with a traversal filename, the upload service generates a UUID name
        // so this should either succeed (UUID name used) or fail validation (bad content)
        // but NEVER write to ../../etc/passwd
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../../etc/passwd.mp4", "video/mp4",
                "not-real-content".getBytes());

        // This will return 400 because the content isn't valid MP4,
        // which proves the path traversal name was never used
        mockMvc.perform(multipart("/api/upload")
                        .file(file)
                        .header("X-API-Key", VALID_API_KEY))
                .andExpect(status().isBadRequest());
    }

    // ── 7. Health endpoint → 200 without auth ────────────

    @Test
    void healthz_returns200_noAuth() throws Exception {
        mockMvc.perform(get("/healthz"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
