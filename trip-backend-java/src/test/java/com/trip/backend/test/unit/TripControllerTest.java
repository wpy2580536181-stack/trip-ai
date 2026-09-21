package com.trip.backend.test.unit;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.service.TripService;
import com.trip.backend.web.controller.TripController;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TripControllerTest {

    @Test
    void confirmCallsServiceAndReturnsTripId() {
        StubTripService service = new StubTripService("confirm");
        TripController controller = new TripController(service);

        ResponseEntity<Map<String, Object>> response = controller.confirmTrip(1L, 7L);

        assertEquals(7L, ((Map<?, ?>) response.getBody().get("data")).get("id"));
        assertEquals(200, response.getBody().get("code"));
        assertEquals(1L, service.lastUserId);
    }

    @Test
    void discardCallsServiceAndReturnsTripId() {
        StubTripService service = new StubTripService("discard");
        TripController controller = new TripController(service);

        ResponseEntity<Map<String, Object>> response = controller.discardTrip(1L, 8L);

        assertEquals(8L, ((Map<?, ?>) response.getBody().get("data")).get("id"));
        assertEquals(200, response.getBody().get("code"));
        assertEquals(1L, service.lastUserId);
    }

    private static class StubTripService extends TripService {

        private final String action;
        private Long lastUserId;

        StubTripService(String action) {
            super(null, null, null);
            this.action = action;
        }

        @Override
        public Trip confirmTrip(Long userId, Long tripId) {
            lastUserId = userId;
            return tripWithId(tripId);
        }

        @Override
        public Trip discardTrip(Long userId, Long tripId) {
            lastUserId = userId;
            return tripWithId(tripId);
        }

        private Trip tripWithId(Long id) {
            Trip trip = Trip.create(1L, "成都", 3, 5000);
            trip.setId(id);
            trip.setStatus("confirm".equals(action) ? "completed" : "discarded");
            return trip;
        }
    }
}
