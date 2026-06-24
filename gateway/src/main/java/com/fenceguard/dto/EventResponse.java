package com.fenceguard.dto;

import java.util.Map;

/**
 * Response DTO for tracking events.
 */
public record EventResponse(
        String id,
        String sessionId,
        String type,
        String severity,
        double timestamp,
        long frameId,
        Map<String, Object> metrics,
        Map<String, Object> headImpactRisk
) {}
