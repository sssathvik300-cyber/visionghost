package com.fenceguard.model;

import java.time.Instant;

/**
 * Internal model representing an active or completed tracking session.
 */
public class SessionInfo {
    private final String sessionId;
    private final String source;
    private final Instant startTime;
    private volatile Instant endTime;
    private volatile boolean active;
    private volatile String uploadPath;

    public SessionInfo(String sessionId, String source) {
        this.sessionId = sessionId;
        this.source = source;
        this.startTime = Instant.now();
        this.active = false;
    }

    public String getSessionId() { return sessionId; }
    public String getSource() { return source; }
    public Instant getStartTime() { return startTime; }
    public Instant getEndTime() { return endTime; }
    public boolean isActive() { return active; }
    public String getUploadPath() { return uploadPath; }

    public void setActive(boolean active) {
        this.active = active;
        if (!active && endTime == null) {
            this.endTime = Instant.now();
        }
    }

    public void setUploadPath(String path) { this.uploadPath = path; }
}
