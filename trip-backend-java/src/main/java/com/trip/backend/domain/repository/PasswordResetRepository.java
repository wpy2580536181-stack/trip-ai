package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.PasswordReset;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.OffsetDateTime;
import java.util.Optional;

/**
 * PasswordReset Repository
 */
public interface PasswordResetRepository extends JpaRepository<PasswordReset, Integer> {

    Optional<PasswordReset> findByToken(String token);

    Optional<PasswordReset> findByEmailAndUsedFalse(String email);

    void deleteByEmailAndExpiresAtBefore(String email, OffsetDateTime dateTime);
}
