package com.trip.backend.test.unit;

import com.trip.backend.domain.entity.Role;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.RoleRepository;
import com.trip.backend.domain.repository.UserRepository;
import com.trip.backend.infra.security.JwtAuthFilter;
import com.trip.backend.infra.security.JwtUtil;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class JwtAuthFilterTest {

    private static final String SECRET = "test-secret-that-is-long-enough-for-hmac-sha-256";

    private final UserRepository userRepository = mock(UserRepository.class);
    private final RoleRepository roleRepository = mock(RoleRepository.class);
    private final JwtAuthFilter filter = new JwtAuthFilter(SECRET, userRepository, roleRepository);
    private final JwtUtil jwtUtil = new JwtUtil(SECRET, 1);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void assignsAdminRoleFromDatabase() throws Exception {
        Long userId = 1L;
        User user = new User();
        user.setId(userId);
        user.setRoleId(1);
        Role admin = new Role("ADMIN");
        admin.setId(1);
        when(userRepository.findById(userId)).thenReturn(Optional.of(user));
        when(roleRepository.findById(1)).thenReturn(Optional.of(admin));

        MockHttpServletRequest request = authorizedRequest(userId, 1);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        assertTrue(authentication.getAuthorities().stream()
            .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority())));
        assertEquals("ADMIN", request.getAttribute("roleName"));
    }

    @Test
    void clearsSecurityContextWhenHeaderMissing() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken("stale-user", null, List.of())
        );

        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void clearsSecurityContextOnInvalidAuthorizationHeader() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken("stale-user", null, List.of())
        );

        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Basic abc");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertEquals(401, response.getStatus());
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void assignsUserRoleFromDatabase() throws Exception {
        Long userId = 2L;
        User user = new User();
        user.setId(userId);
        user.setRoleId(2);
        Role normal = new Role("USER");
        normal.setId(2);
        when(userRepository.findById(userId)).thenReturn(Optional.of(user));
        when(roleRepository.findById(2)).thenReturn(Optional.of(normal));

        MockHttpServletRequest request = authorizedRequest(userId, 2);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        assertTrue(authentication.getAuthorities().stream()
            .anyMatch(authority -> "ROLE_USER".equals(authority.getAuthority())));
        assertTrue(authentication.getAuthorities().stream()
            .noneMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority())));
    }

    @Test
    void rejectsTokenForMissingUser() throws Exception {
        Long userId = 99L;
        when(userRepository.findById(userId)).thenReturn(Optional.empty());
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken("stale-user", null, List.of())
        );

        MockHttpServletRequest request = authorizedRequest(userId, 2);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertEquals(401, response.getStatus());
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    private MockHttpServletRequest authorizedRequest(Long userId, Integer roleId) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer " + jwtUtil.generateToken("tester", userId, roleId));
        return request;
    }
}
