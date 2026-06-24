package com.fenceguard.api;

import com.fenceguard.dto.EventResponse;
import com.fenceguard.model.TrackingEvent;
import com.fenceguard.service.EventStore;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Event query endpoint — returns the event log for a session.
 */
@RestController
@RequestMapping("/api")
public class EventController {

    private final EventStore eventStore;

    public EventController(EventStore eventStore) {
        this.eventStore = eventStore;
    }

    @GetMapping("/events")
    public ResponseEntity<List<EventResponse>> getEvents(
            @RequestParam String sessionId) {

        if (sessionId == null || sessionId.isBlank()) {
            throw new IllegalArgumentException("sessionId is required");
        }

        List<EventResponse> events = eventStore.getEvents(sessionId).stream()
                .map(this::toResponse)
                .toList();

        return ResponseEntity.ok(events);
    }

    private EventResponse toResponse(TrackingEvent event) {
        return new EventResponse(
                event.id(),
                event.sessionId(),
                event.type(),
                event.severity(),
                event.timestamp(),
                event.frameId(),
                event.metrics(),
                event.headImpactRisk()
        );
    }
}
