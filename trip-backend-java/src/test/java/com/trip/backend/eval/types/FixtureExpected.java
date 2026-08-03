package com.trip.backend.eval.types;

import java.util.List;

/**
 * Fixture expected 节
 */
public class FixtureExpected {
    private String city = "";
    private List<String> spotNames = List.of();
    private List<PoiMatch> mustContainPois = List.of();
    private List<String> mustContainKeywords = List.of();
    private List<String> mustNotContainKeywords = List.of();
    private int days = 0;
    private boolean jsonValid = false;
    private boolean isRecommendation = false;
    private boolean isDetailAnswer = false;
    private int maxActivitiesPerDay = 0;
    private List<ToolCallRule> toolCalls = List.of();
    private boolean activitiesHavePriceField = false;
    private boolean containsPriceNumber = false;
    private String groundTruth = "";
    private String keywordMatchMode = "all";

    public FixtureExpected() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public List<String> getSpotNames() {
        return spotNames;
    }

    public void setSpotNames(List<String> spotNames) {
        this.spotNames = spotNames;
    }

    public List<PoiMatch> getMustContainPois() {
        return mustContainPois;
    }

    public void setMustContainPois(List<PoiMatch> mustContainPois) {
        this.mustContainPois = mustContainPois;
    }

    public List<String> getMustContainKeywords() {
        return mustContainKeywords;
    }

    public void setMustContainKeywords(List<String> mustContainKeywords) {
        this.mustContainKeywords = mustContainKeywords;
    }

    public List<String> getMustNotContainKeywords() {
        return mustNotContainKeywords;
    }

    public void setMustNotContainKeywords(List<String> mustNotContainKeywords) {
        this.mustNotContainKeywords = mustNotContainKeywords;
    }

    public int getDays() {
        return days;
    }

    public void setDays(int days) {
        this.days = days;
    }

    public boolean isJsonValid() {
        return jsonValid;
    }

    public void setJsonValid(boolean jsonValid) {
        this.jsonValid = jsonValid;
    }

    public boolean isRecommendation() {
        return isRecommendation;
    }

    public void setRecommendation(boolean recommendation) {
        this.isRecommendation = recommendation;
    }

    public boolean isDetailAnswer() {
        return isDetailAnswer;
    }

    public void setDetailAnswer(boolean detailAnswer) {
        isDetailAnswer = detailAnswer;
    }

    public int getMaxActivitiesPerDay() {
        return maxActivitiesPerDay;
    }

    public void setMaxActivitiesPerDay(int maxActivitiesPerDay) {
        this.maxActivitiesPerDay = maxActivitiesPerDay;
    }

    public List<ToolCallRule> getToolCalls() {
        return toolCalls;
    }

    public void setToolCalls(List<ToolCallRule> toolCalls) {
        this.toolCalls = toolCalls;
    }

    public boolean isActivitiesHavePriceField() {
        return activitiesHavePriceField;
    }

    public void setActivitiesHavePriceField(boolean activitiesHavePriceField) {
        this.activitiesHavePriceField = activitiesHavePriceField;
    }

    public boolean isContainsPriceNumber() {
        return containsPriceNumber;
    }

    public void setContainsPriceNumber(boolean containsPriceNumber) {
        this.containsPriceNumber = containsPriceNumber;
    }

    public String getGroundTruth() {
        return groundTruth;
    }

    public void setGroundTruth(String groundTruth) {
        this.groundTruth = groundTruth;
    }

    public String getKeywordMatchMode() {
        return keywordMatchMode;
    }

    public void setKeywordMatchMode(String keywordMatchMode) {
        this.keywordMatchMode = keywordMatchMode;
    }
}
