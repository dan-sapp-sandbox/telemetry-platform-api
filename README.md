# Telemetry Platform API

Backend services for a real-time maritime and aviation telemetry platform.

The API ingests, processes, stores, and distributes live AIS (Automatic Identification System) and ADS-B (Automatic Dependent Surveillance-Broadcast) telemetry data for visualization and analysis. It provides WebSocket-based streaming, spatial filtering, trajectory management, and historical data access for frontend clients.

## Features

* Real-time AIS vessel tracking
* Real-time ADS-B aircraft tracking
* WebSocket telemetry streaming
* Geographic bounding-box filtering
* Historical track retrieval
* Position interpolation support
* PostgreSQL/PostGIS spatial storage
* REST and WebSocket APIs
* High-frequency telemetry processing
* Support for AI Command Layer

## Tech Stack

### Backend

* FastAPI
* Python
* SQLAlchemy
* PostgreSQL
* PostGIS
* WebSockets

### Geospatial

* PostGIS
* GeoJSON
* Spatial Indexes

## API Capabilities

### Entity Retrieval

Retrieve vessels and aircraft within a geographic extent.

### Historical Tracks

Access historical position reports and trajectory data.

### Real-Time Streaming

Subscribe to live telemetry updates through WebSocket connections.

### Spatial Filtering

Query entities by map extent and location.

## Data Sources

### AIS

Automatic Identification System (AIS) messages provide vessel position, speed, heading, and identification information.

### ADS-B

Automatic Dependent Surveillance-Broadcast (ADS-B) messages provide aircraft position, altitude, velocity, and identification information.


This project explores the design of scalable real-time telemetry systems, combining geospatial data processing, live streaming architectures, and interactive operational visualization tools.
