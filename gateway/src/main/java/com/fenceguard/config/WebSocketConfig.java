package com.fenceguard.config;

import com.fenceguard.websocket.VideoStreamHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocket configuration — registers the video stream handler at /ws.
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final VideoStreamHandler videoStreamHandler;

    public WebSocketConfig(VideoStreamHandler videoStreamHandler) {
        this.videoStreamHandler = videoStreamHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(videoStreamHandler, "/ws")
                .setAllowedOriginPatterns("http://127.0.0.1:*", "http://localhost:*");
    }
}
