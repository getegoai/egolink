# Multi-stage build for Ego Cloud Enterprise Backend
FROM maven:3.9-eclipse-temurin-17-alpine AS build

WORKDIR /build

# Copy pom.xml and source
COPY pom.xml .
COPY src ./src

# Build artifact without running unit tests (clean & fast)
RUN mvn clean package -DskipTests

# Runtime Stage
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

RUN addgroup -S egogroup && adduser -S egouser -G egogroup \
    && mkdir -p /app/data/cold && chown -R egouser:egogroup /app

# Copy compiled JAR from build stage
COPY --from=build /build/target/ego-cloud-backend-*.jar app.jar

USER egouser

EXPOSE 8080

ENTRYPOINT ["java", "-Xms256m", "-Xmx2048m", "-Djava.security.egd=file:/dev/./urandom", "-jar", "app.jar"]
