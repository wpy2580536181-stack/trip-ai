package com.trip.backend.test.unit;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.repository.TripRepository;
import com.trip.backend.service.TripService;
import com.trip.backend.utils.AppException;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TripServiceTest {

    private final TripRepository tripRepository = mock(TripRepository.class);
    private final TripService tripService = new TripService(tripRepository, null, null);

    @Test
    void confirmTransitionsOwnedCandidateToCompleted() {
        Trip trip = candidateTrip(7L, 1L);
        when(tripRepository.findByIdAndUserId(7L, 1L)).thenReturn(Optional.of(trip));
        when(tripRepository.save(any(Trip.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Trip confirmed = tripService.confirmTrip(1L, 7L);

        assertEquals("completed", confirmed.getStatus());
        verify(tripRepository).findByIdAndUserId(7L, 1L);
    }

    @Test
    void discardTransitionsOwnedCandidateToDiscarded() {
        Trip trip = candidateTrip(8L, 1L);
        when(tripRepository.findByIdAndUserId(8L, 1L)).thenReturn(Optional.of(trip));
        when(tripRepository.save(any(Trip.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Trip discarded = tripService.discardTrip(1L, 8L);

        assertEquals("discarded", discarded.getStatus());
    }

    @Test
    void rejectsConfirmingAnotherUsersTrip() {
        when(tripRepository.findByIdAndUserId(9L, 1L)).thenReturn(Optional.empty());

        AppException exception = assertThrows(
            AppException.class,
            () -> tripService.confirmTrip(1L, 9L)
        );

        assertEquals(404, exception.getStatusCode());
        verify(tripRepository, never()).save(any());
    }

    @Test
    void rejectsConfirmingNonCandidateStatus() {
        Trip trip = candidateTrip(10L, 1L);
        trip.setStatus("completed");
        when(tripRepository.findByIdAndUserId(10L, 1L)).thenReturn(Optional.of(trip));

        AppException exception = assertThrows(
            AppException.class,
            () -> tripService.confirmTrip(1L, 10L)
        );

        assertEquals(400, exception.getStatusCode());
        verify(tripRepository, never()).save(any());
    }

    private Trip candidateTrip(Long id, Long userId) {
        Trip trip = Trip.create(userId, "成都", 3, 5000);
        trip.setId(id);
        return trip;
    }
}
