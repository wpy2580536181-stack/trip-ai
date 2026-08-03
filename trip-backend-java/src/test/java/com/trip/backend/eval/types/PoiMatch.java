package com.trip.backend.eval.types;

import java.util.List;

/**
 * POI 匹配规则
 */
public class PoiMatch {
    private String name;
    private String nameContains;
    private String city;
    private String cityNearby;

    public PoiMatch() {
    }

    public PoiMatch(String name, String nameContains, String city, String cityNearby) {
        this.name = name;
        this.nameContains = nameContains;
        this.city = city;
        this.cityNearby = cityNearby;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getNameContains() {
        return nameContains;
    }

    public void setNameContains(String nameContains) {
        this.nameContains = nameContains;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getCityNearby() {
        return cityNearby;
    }

    public void setCityNearby(String cityNearby) {
        this.cityNearby = cityNearby;
    }
}
