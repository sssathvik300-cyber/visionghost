package com.fenceguard.grpc;

import com.fenceguard.config.AppProperties;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import io.grpc.stub.StreamObserver;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * gRPC client that connects to the Python CV worker on localhost.
 * Streams annotated frames + events back to the gateway for WebSocket relay.
 */
@Component
public class CvWorkerClient {

    private static final Logger log = LoggerFactory.getLogger(CvWorkerClient.class);
    private static final Metadata.Key<String> TOKEN_KEY =
            Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    private final AppProperties appProperties;
    private ManagedChannel channel;
    private CvWorkerGrpc.CvWorkerStub asyncStub;

    public CvWorkerClient(AppProperties appProperties) {
        this.appProperties = appProperties;
    }

    @PostConstruct
    public void init() {
        String target = appProperties.grpc().host() + ":" + appProperties.grpc().port();
        log.info("Connecting to CV worker at {}", target);

        channel = ManagedChannelBuilder
                .forAddress(appProperties.grpc().host(), appProperties.grpc().port())
                .usePlaintext() // localhost only — no TLS needed
                .maxInboundMessageSize(16 * 1024 * 1024) // 16MB for JPEG frames
                .build();

        // Attach internal token to all calls
        Metadata headers = new Metadata();
        headers.put(TOKEN_KEY, appProperties.internalToken());

        asyncStub = CvWorkerGrpc.newStub(channel)
                .withInterceptors(MetadataUtils.newAttachHeadersInterceptor(headers));
    }

    @PreDestroy
    public void shutdown() {
        if (channel != null) {
            try {
                channel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                channel.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    /**
     * Start streaming frames from the CV worker.
     *
     * @param sessionId Unique session identifier
     * @param source    "webcam" or file path
     * @param onFrame   Callback for each frame received
     * @param onError   Callback for errors
     * @param onComplete Callback when stream completes
     */
    public void startStreaming(String sessionId, String source,
                                Consumer<FrameData> onFrame,
                                Consumer<Throwable> onError,
                                Runnable onComplete) {

        SessionConfig config = SessionConfig.newBuilder()
                .setSessionId(sessionId)
                .setSource(source)
                .setInternalToken(appProperties.internalToken())
                .build();

        asyncStub.streamSession(config, new StreamObserver<FrameData>() {
            @Override
            public void onNext(FrameData frame) {
                onFrame.accept(frame);
            }

            @Override
            public void onError(Throwable t) {
                log.error("CV worker stream error for session {}", sessionId, t);
                onError.accept(t);
            }

            @Override
            public void onCompleted() {
                log.info("CV worker stream completed for session {}", sessionId);
                onComplete.run();
            }
        });
    }

    /**
     * Stop a running session on the CV worker.
     */
    public void stopStreaming(String sessionId) {
        StopRequest request = StopRequest.newBuilder()
                .setSessionId(sessionId)
                .build();

        // Use blocking stub for stop
        try {
            CvWorkerGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .stopSession(request);
        } catch (Exception e) {
            log.warn("Error stopping CV worker session {}: {}", sessionId, e.getMessage());
        }
    }

    /**
     * Check if the gRPC channel is connected.
     */
    public boolean isConnected() {
        return channel != null && !channel.isShutdown() && !channel.isTerminated();
    }
}
