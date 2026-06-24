package com.fenceguard.api;

import com.fenceguard.dto.SessionStartRequest;
import com.fenceguard.model.SessionInfo;
import com.fenceguard.service.SessionService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Session lifecycle endpoints — start/stop tracking processing.
 */
@RestController
@RequestMapping("/api/session")
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @PostMapping("/start")
    public ResponseEntity<Map<String, Object>> startSession(
            @Valid @RequestBody SessionStartRequest request) {

        // If source is "webcam", create a new session; otherwise look up existing
        SessionInfo session;
        if ("webcam".equalsIgnoreCase(request.source())) {
            session = sessionService.createSession("webcam");
        } else {
            // Source should be a session ID from a prior upload
            session = sessionService.getSession(request.source())
                    .orElseThrow(() -> new IllegalArgumentException(
                            "Session not found: " + request.source()));
        }

        sessionService.startSession(session.getSessionId());

        return ResponseEntity.ok(Map.of(
                "sessionId", session.getSessionId(),
                "source", session.getSource(),
                "status", "started"
        ));
    }

    @PostMapping("/stop")
    public ResponseEntity<Map<String, Object>> stopSession(
            @RequestBody Map<String, String> body) {

        String sessionId = body.get("sessionId");
        if (sessionId == null || sessionId.isBlank()) {
            throw new IllegalArgumentException("sessionId is required");
        }

        return sessionService.stopSession(sessionId)
                .map(session -> ResponseEntity.ok(Map.<String, Object>of(
                        "sessionId", session.getSessionId(),
                        "status", "stopped"
                )))
                .orElseThrow(() -> new IllegalArgumentException(
                        "Session not found: " + sessionId));
    }
}
