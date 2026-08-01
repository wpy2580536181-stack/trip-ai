package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Role;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Role Repository
 */
public interface RoleRepository extends JpaRepository<Role, Integer> {
}
