package com.trip.backend.test.unit;

import com.trip.backend.infra.security.JwtUtil;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtUtilTest {

    @Test
    void acceptsSecretWithEnoughEntropy() {
        new JwtUtil("test-secret-that-is-long-enough-for-hmac-sha-256", 7);
    }

    @Test
    void rejectsBlankSecret() {
        assertThrows(IllegalStateException.class, () -> JwtUtil.validateSecret(""));
        assertThrows(IllegalStateException.class, () -> JwtUtil.validateSecret(null));
    }

    @Test
    void rejectsShortSecret() {
        assertThrows(IllegalStateException.class, () -> JwtUtil.validateSecret("too-short"));
    }
}
