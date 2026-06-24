package com.fenceguard.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * Request to start a tracking session.
 * Jackson is configured to FAIL_ON_UNKNOWN_PROPERTIES so unexpected fields are rejected.
 */
public record SessionStartRequest(
        @NotBlank(message = "Source is required")
        @Pattern(regexp = "^(webcam|[a-zA-Z0-9_.\\-/\\\\:]+)$",
                 message = "Source must be 'webcam' or a valid file identifier")
        String source
) {}
