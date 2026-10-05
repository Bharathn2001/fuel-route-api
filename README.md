# Fuel Route API

A Django REST API for fuel-efficient route planning across the USA.

## Features

- Start and destination based route calculation
- OSRM routing integration
- Fuel stations from the provided fuel-price dataset
- Fuel stations filtered near the route
- Cost-effective fuel stop selection
- Vehicle maximum range of 500 miles
- Multiple fuel stops for long routes
- Default vehicle efficiency of 10 MPG
- Total fuel consumption and estimated fuel cost
- Single OSRM routing API call per request

## Tech Stack

- Python
- Django
- Django REST Framework
- SQLite
- OSRM
- Requests

## API Endpoint

```text
GET /api/route/