#!/bin/bash
cd /Users/wang/Documents/trip/trip-backend-java
mvn clean compile -DskipTests 2>&1 | tail -20
EXIT_CODE=${PIPESTATUS[0]}
exit $EXIT_CODE
