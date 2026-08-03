package com.trip.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        System.setProperty("spring.jpa.show-sql", "true");
        System.setProperty("logging.level.org.hibernate", "DEBUG");
        SpringApplication app = new SpringApplication(Application.class);
        app.setAdditionalProfiles("debug");
        app.run(args);
    }
}
