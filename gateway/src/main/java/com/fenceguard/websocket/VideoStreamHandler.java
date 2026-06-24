package com.fenceguard.websocket;

import com.fenceguard.config.AppProperties;
import com.fenceguard.grpc.CvWorkerClient;
import com.fenceguard.grpc.FrameData;
import com.fenceguard.model.TrackingEvent;
import com.fenceguard.service.EventStore;
import com.fenceguard.service.SessionService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket handler that:
 * 1. Validates the API token on handshake (token query param)
 * 2. Connects to the CV worker via gRPC
 * 3. Relays annotated JPEG frames as binary WS messages
 * 4. Relays metrics + events as JSON text WS messages
 * 5. Stores events in EventStore for REST API queries
 */
@Component
public class VideoStreamHandler extends AbstractWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(VideoStreamHandler.class);

    private final AppProperties appProperties;
    private final CvWorkerClient cvWorkerClient;
    private final SessionService sessionService;
    private final EventStore eventStore;
    private final ObjectMapper objectMapper = new ObjectMapper();

    // Track which WS session maps to which tracking session
    private final Map<String, String> wsToTrackingSession = new ConcurrentHashMap<>();

    public VideoStreamHandler(AppProperties appProperties,
                                CvWorkerClient cvWorkerClient,
                                SessionService sessionService,
                                EventStore eventStore) {
        this.appProperties = appProperties;
        this.cvWorkerClient = cvWorkerClient;
        this.sessionService = sessionService;
        this.eventStore = eventStore;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        // 1. Validate token from query param
        String token = extractToken(session);
        if (token == null || !isTokenValid(token)) {
            log.warn("WS connection rejected — invalid token from {}",
                    session.getRemoteAddress());
            session.close(new CloseStatus(1008, "Invalid token"));
            return;
        }

        // 2. Find the active tracking session
        var activeSession = sessionService.getActiveSession();
        if (activeSession.isEmpty()) {
            session.close(new CloseStatus(1008, "No active session"));
            return;
        }

        String trackingSessionId = activeSession.get().getSessionId();
        String source = activeSession.get().getSource();
        wsToTrackingSession.put(session.getId(), trackingSessionId);

        log.info("WS connected: {} → session {}", session.getId(), trackingSessionId);

        // 3. Start gRPC streaming from CV worker
        cvWorkerClient.startStreaming(
                trackingSessionId,
                source,
                // onFrame
                frameData -> handleFrame(session, frameData, trackingSessionId),
                // onError
                error -> {
                    log.error("Stream error for WS {}: {}", session.getId(), error.getMessage());
                    try {
                        if (session.isOpen()) {
                            session.sendMessage(new TextMessage(
                                    "{\"type\":\"error\",\"message\":\"CV worker error\"}"));
                        }
                    } catch (IOException ignored) {}
                },
                // onComplete
                () -> {
                    log.info("Stream completed for WS {}", session.getId());
                    try {
                        if (session.isOpen()) {
                            session.sendMessage(new TextMessage(
                                    "{\"type\":\"complete\",\"message\":\"Processing finished\"}"));
                        }
                    } catch (IOException ignored) {}
                }
        );
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String trackingSessionId = wsToTrackingSession.remove(session.getId());
        if (trackingSessionId != null) {
            cvWorkerClient.stopStreaming(trackingSessionId);
            sessionService.stopSession(trackingSessionId);
            log.info("WS disconnected: {} (session {})", session.getId(), trackingSessionId);
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        // Client can send control messages (e.g., stop)
        String payload = message.getPayload();
        if ("stop".equals(payload)) {
            String trackingSessionId = wsToTrackingSession.get(session.getId());
            if (trackingSessionId != null) {
                cvWorkerClient.stopStreaming(trackingSessionId);
                sessionService.stopSession(trackingSessionId);
            }
        }
    }

    private void handleFrame(WebSocketSession session, FrameData frameData,
                               String trackingSessionId) {
        synchronized (session) {
            try {
                if (!session.isOpen()) return;

                // Send annotated JPEG frame as binary
                if (!frameData.getJpegFrame().isEmpty()) {
                    session.sendMessage(new BinaryMessage(
                            frameData.getJpegFrame().toByteArray()));
                }

                // Send metrics as JSON text
                if (!frameData.getMetricsJson().isEmpty()) {
                    session.sendMessage(new TextMessage(
                            "{\"type\":\"metrics\",\"data\":" +
                            frameData.getMetricsJson() +
                            ",\"frameId\":" + frameData.getFrameId() +
                            ",\"fps\":" + String.format("%.1f", frameData.getFps()) + "}"));
                }

                // Send events as JSON text + store them
                if (!frameData.getEventsJson().isEmpty() &&
                    !frameData.getEventsJson().equals("[]")) {
                    session.sendMessage(new TextMessage(
                            "{\"type\":\"events\",\"data\":" +
                            frameData.getEventsJson() + "}"));

                    // Parse and store events
                    storeEvents(trackingSessionId, frameData);
                }

                // Send inset frame periodically (every 3rd frame to save bandwidth)
                if (frameData.getFrameId() % 3 == 0 &&
                    !frameData.getInsetFrame().isEmpty()) {
                    session.sendMessage(new TextMessage(
                            "{\"type\":\"inset\",\"frameId\":" + frameData.getFrameId() + "}"));
                    session.sendMessage(new BinaryMessage(
                            frameData.getInsetFrame().toByteArray()));
                }

            } catch (IOException e) {
                log.warn("Failed to send frame to WS {}: {}", session.getId(), e.getMessage());
            }
        }
    }

    private void storeEvents(String sessionId, FrameData frameData) {
        try {
            List<Map<String, Object>> events = objectMapper.readValue(
                    frameData.getEventsJson(),
                    new TypeReference<List<Map<String, Object>>>() {});

            for (Map<String, Object> event : events) {
                @SuppressWarnings("unchecked")
                Map<String, Object> metrics = (Map<String, Object>) event.get("metrics");
                @SuppressWarnings("unchecked")
                Map<String, Object> headImpactRisk =
                        (Map<String, Object>) event.get("head_impact_risk");

                eventStore.addEvent(new TrackingEvent(
                        UUID.randomUUID().toString().substring(0, 8),
                        sessionId,
                        (String) event.get("type"),
                        (String) event.get("severity"),
                        ((Number) event.getOrDefault("timestamp", 0.0)).doubleValue(),
                        frameData.getFrameId(),
                        metrics,
                        headImpactRisk
                ));
            }
        } catch (Exception e) {
            log.warn("Failed to parse events: {}", e.getMessage());
        }
    }

    private String extractToken(WebSocketSession session) {
        if (session.getUri() == null) return null;
        var params = UriComponentsBuilder.fromUri(session.getUri())
                .build().getQueryParams();
        List<String> tokens = params.get("token");
        return (tokens != null && !tokens.isEmpty()) ? tokens.get(0) : null;
    }

    private boolean isTokenValid(String token) {
        byte[] expectedBytes = appProperties.apiKey()
                .getBytes(StandardCharsets.UTF_8);
        byte[] providedBytes = token.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expectedBytes, providedBytes);
    }
}
