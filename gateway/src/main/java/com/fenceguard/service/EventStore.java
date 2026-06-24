package com.fenceguard.service;

import com.fenceguard.model.TrackingEvent;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory event store for tracking events.
 * Thread-safe — events are appended from the gRPC relay thread
 * and read from the REST API thread.
 */
@Service
public class EventStore {

    private final Map<String, List<TrackingEvent>> eventsBySession = new ConcurrentHashMap<>();

    /**
     * Store a new event for a session.
     */
    public void addEvent(TrackingEvent event) {
        eventsBySession
                .computeIfAbsent(event.sessionId(), k -> Collections.synchronizedList(new ArrayList<>()))
                .add(event);
    }

    /**
     * Get all events for a session, ordered by timestamp.
     */
    public List<TrackingEvent> getEvents(String sessionId) {
        List<TrackingEvent> events = eventsBySession.get(sessionId);
        return events != null ? List.copyOf(events) : List.of();
    }

    /**
     * Clear events for a session (called on session cleanup).
     */
    public void clearSession(String sessionId) {
        eventsBySession.remove(sessionId);
    }
}
