# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -q -e -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

# ---- runtime stage ----
FROM eclipse-temurin:21-jre
WORKDIR /app

# 模型文件（ONNX 导出产物，不入 git；本地构建时需已存在）
COPY models/ ./models/

# 应用 jar
COPY --from=build /build/target/*.jar app.jar

EXPOSE 8000
ENV JAVA_OPTS="-Xms512m -Xmx1g"
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.jar"]
