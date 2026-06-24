package com.fenceguard.service;

import com.fenceguard.model.SessionInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Manages the lifecycle of tracking sessions.
 */
@Service
public class SessionService {

    private static final Logger log = LoggerFactory.getLogger(SessionService.class);

    private final Map<String, SessionInfo> sessions = new ConcurrentHashMap<>();

    /**
     * Create a new session for an upload-based source.
     */
    public SessionInfo createSession(String source) {
        String sessionId = UUID.randomUUID().toString().substring(0, 8);
        SessionInfo session = new SessionInfo(sessionId, source);
        sessions.put(sessionId, session);
        log.info("Session created: {} (source={})", sessionId, source);
        return session;
    }

    /**
     * Start processing for a session.
     */
    public Optional<SessionInfo> startSession(String sessionId) {
        SessionInfo session = sessions.get(sessionId);
        if (session == null) return Optional.empty();
        session.setActive(true);
        log.info("Session started: {}", sessionId);
        return Optional.of(session);
    }

    /**
     * Stop processing for a session.
     */
    public Optional<SessionInfo> stopSession(String sessionId) {
        SessionInfo session = sessions.get(sessionId);
        if (session == null) return Optional.empty();
        session.setActive(false);
        log.info("Session stopped: {}", sessionId);
        return Optional.of(session);
    }

    /**
     * Get a session by ID.
     */
    public Optional<SessionInfo> getSession(String sessionId) {
        return Optional.ofNullable(sessions.get(sessionId));
    }

    /**
     * Get the currently active session, if any.
     */
    public Optional<SessionInfo> getActiveSession() {
        return sessions.values().stream()
                .filter(SessionInfo::isActive)
                .findFirst();
    }
}
