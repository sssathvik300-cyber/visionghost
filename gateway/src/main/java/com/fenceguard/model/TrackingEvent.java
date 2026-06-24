package com.fenceguard.model;

import java.util.Map;

/**
 * Internal model for a detected tracking event.
 */
public record TrackingEvent(
        String id,
        String sessionId,
        String type,
        String severity,
        double timestamp,
        long frameId,
        Map<String, Object> metrics,
        Map<String, Object> headImpactRisk
) {}
