package com.fenceguard.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.security.MessageDigest;
import java.util.List;

/**
 * API Key authentication filter.
 * Validates X-API-Key header using constant-time comparison (MessageDigest.isEqual)
 * to prevent timing attacks.
 */
public class ApiKeyFilter extends OncePerRequestFilter {

    private static final String API_KEY_HEADER = "X-API-Key";
    private final byte[] expectedKeyBytes;

    public ApiKeyFilter(String expectedKey) {
        this.expectedKeyBytes = expectedKey.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                     HttpServletResponse response,
                                     FilterChain filterChain)
            throws ServletException, IOException {

        String path = request.getRequestURI();

        // Skip auth for public endpoints
        if (isPublicPath(path)) {
            filterChain.doFilter(request, response);
            return;
        }

        // Only require auth for /api/** paths
        if (!path.startsWith("/api/")) {
            filterChain.doFilter(request, response);
            return;
        }

        String providedKey = request.getHeader(API_KEY_HEADER);
        if (providedKey == null || !isKeyValid(providedKey)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"type\":\"about:blank\",\"title\":\"Unauthorized\"," +
                    "\"status\":401,\"detail\":\"Valid API key required\"}");
            return;
        }

        // Set authentication in security context
        var auth = new UsernamePasswordAuthenticationToken(
                "api-client", null,
                List.of(new SimpleGrantedAuthority("ROLE_API_CLIENT"))
        );
        SecurityContextHolder.getContext().setAuthentication(auth);

        filterChain.doFilter(request, response);
    }

    private boolean isPublicPath(String path) {
        return path.equals("/healthz")
                || path.equals("/")
                || path.equals("/index.html")
                || path.startsWith("/css/")
                || path.startsWith("/js/")
                || path.equals("/favicon.ico");
    }

    /**
     * Constant-time comparison to prevent timing side-channel attacks.
     */
    private boolean isKeyValid(String providedKey) {
        byte[] providedBytes = providedKey.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expectedKeyBytes, providedBytes);
    }
}
