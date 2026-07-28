# Ride Dispatch API

## 1. Project Overview

The **Ride Dispatch API** is a Django REST Framework service for managing rides, riders, drivers, and the ride lifecycle events that track a ride's progress (e.g. pickup, dropoff). It exposes an admin-facing API for listing, filtering, and sorting rides, and is designed from the ground up around **predictable, high-performance database access** rather than convenience-first ORM usage. The service runs fully containerized on PostgreSQL/PostGIS and ships with interactive OpenAPI documentation via Swagger UI.

---

## 2. Architecture & Tech Stack

| Layer            | Technology                                 |
| ---------------- | ------------------------------------------- |
| Language         | Python 3.12                                 |
| Framework        | Django 5.1 + Django REST Framework 3.15     |
| Database         | PostgreSQL 16 with the PostGIS 3.4 extension |
| Filtering        | `django-filter`                             |
| API Docs         | `drf-spectacular` (OpenAPI 3 + Swagger UI)  |
| Containerization | Docker + Docker Compose                     |

### Performance design

The core engineering constraint on this project is **database performance, not just correctness**. The `rides` list endpoint is explicitly engineered to stay within a **strict 2–3 query budget**, no matter how many rides or events exist in the database:

```python
Ride.objects.select_related("id_rider", "id_driver")     # query 1: rides + rider/driver joined
    .prefetch_related(
        Prefetch(
            "events",
            queryset=Ride_Event.objects.filter(created_at__gte=yesterday),
            to_attr="todays_ride_events",                 # query 2: bounded event fetch
        )
    )
# + 1 optional COUNT(*) query issued by pagination
```

- **`select_related("id_rider", "id_driver")`** collapses both rider and driver foreign keys into the initial query via SQL `JOIN`s, so no per-row lookup is ever issued for the related users.
- **`Prefetch(..., to_attr="todays_ride_events")`** loads only the last 24 hours of `Ride_Event` rows in a single additional query, and attaches the filtered result directly onto each `Ride` instance as `todays_ride_events`. The serializer reads that in-memory attribute rather than the full `events` reverse relation, which is what keeps the response N+1-free — filtering happens on already-fetched data instead of firing one query per ride.
- Pagination may add one `COUNT(*)` query, bringing the worst case to **3 queries total** for the entire list endpoint, regardless of page size.

Geographic distance sorting (nearest rides to a given point) is implemented with **standard PostgreSQL math — a Haversine formula via `RawSQL`** — rather than PostGIS geometry functions:

```python
HAVERSINE_SQL = """
(
    6371 * acos(
        cos(radians(%s)) * cos(radians(pickup_latitude))
        * cos(radians(pickup_longitude) - radians(%s))
        + sin(radians(%s)) * sin(radians(pickup_latitude))
    )
)
"""
queryset.annotate(distance=RawSQL(HAVERSINE_SQL, (lat, lon, lat)))
```

This computes distance (in kilometers, using Earth's radius of 6371 km) entirely inside the database, so sorting and pagination happen in Postgres instead of pulling the full table into Python. Because the `Ride` table's pickup coordinates are plain `FloatField`s rather than a PostGIS `PointField`, a parameterized Haversine expression is the most efficient way to rank rides by proximity without requiring a schema/geometry migration, while still leaving PostGIS available as the underlying database engine.

---

## 3. Local Setup Instructions

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Build and start the database + API service
docker-compose up --build

# 2. In a second terminal, apply migrations
docker-compose exec api python manage.py migrate

# 3. Create an admin superuser
docker-compose exec api python manage.py createsuperuser
```

> `createsuperuser` automatically sets `role="admin"` on the new user, so the account it creates can immediately access the admin-only API endpoints.

### A note on the exposed port

The `api` service does **not** bind to a fixed host port. In `docker-compose.yml` it maps a **host port range to the container's port 8000**:

```yaml
ports:
  # Host-port range lets multiple replicas bind distinct ports
  # (first instance -> 8000, next -> 8001, ...). Enables `--scale api=N`.
  - "8000-8010:8000"
```

Docker Compose assigns the **first free port in that range** (`8000`–`8010`) to the container, so the port on your machine may not be `8000` — e.g. if `8000` is already in use, or `--scale api=N` starts multiple replicas, the API might come up on `8001`, `8002`, etc. Always check which port was actually assigned with:

```bash
docker-compose ps
# or
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

Look at the `PORTS` column — it shows the mapping as `0.0.0.0:<host_port>->8000/tcp`. Use `<host_port>` in place of `8000` in every URL below and in the Swagger/curl examples.

---

## 4. API Documentation

Once the stack is running, interactive Swagger UI documentation is available at (replace `8000` with whatever host port was actually assigned — see above):

```
http://localhost:8000/api/docs/
```

(the raw OpenAPI schema is served at `http://localhost:8000/api/schema/`.)

### Authenticating as an Admin user

The API endpoints are restricted to users whose `role` is `"admin"` (enforced by the `IsAdminRole` permission class). To authenticate:

1. Create an admin user with `python manage.py createsuperuser` (see above) — this sets `role="admin"` automatically.
2. Log in at the Django admin site, `http://localhost:8000/admin/` (substituting the actual assigned host port — see [A note on the exposed port](#a-note-on-the-exposed-port)), using that superuser's email and password. This establishes an authenticated session cookie.
3. With that session active, both the Swagger UI and DRF's browsable API will make authenticated requests automatically. Alternatively, HTTP Basic Auth can be used directly against the API, e.g.:

```bash
curl -u admin@example.com:yourpassword \
  "http://localhost:8000/api/rides/?ordering=pickup_time"
```

---

## Bonus - SQL

The following raw SQL statement returns the count of trips whose duration from **Pickup to Dropoff** exceeded 1 hour, grouped by **Month** and **Driver**. It relies on `Ride_Event` rows already populated with the descriptions `'Status changed to pickup'` and `'Status changed to dropoff'`, joined back to `Ride` and `User` to resolve the driver's name.

```sql
WITH pickup_events AS (
    SELECT id_ride, created_at AS pickup_time
    FROM "Ride_Event"
    WHERE description = 'Status changed to pickup'
),
dropoff_events AS (
    SELECT id_ride, created_at AS dropoff_time
    FROM "Ride_Event"
    WHERE description = 'Status changed to dropoff'
),
long_trips AS (
    SELECT 
        p.id_ride, 
        p.pickup_time
    FROM pickup_events p
    JOIN dropoff_events d ON p.id_ride = d.id_ride
    WHERE (d.dropoff_time - p.pickup_time) > INTERVAL '1 hour'
)
SELECT 
    TO_CHAR(lt.pickup_time, 'YYYY-MM') AS "Month",
    u.first_name || ' ' || u.last_name AS "Driver",
    COUNT(lt.id_ride) AS "Count of Trips > 1 hr"
FROM long_trips lt
JOIN "Ride" r ON lt.id_ride = r.id_ride
JOIN "User" u ON r.id_driver = u.id_user
GROUP BY 
    TO_CHAR(lt.pickup_time, 'YYYY-MM'),
    u.first_name,
    u.last_name
ORDER BY 
    "Month" ASC, 
    "Driver" ASC;
```

### Sample report output

| Month | Driver | Count of Trips > 1 hr |
| ----- | ------ | ---------------------- |
| 2024-01 | Chris H | 4 |
| 2024-01 | Howard Y | 5 |
| 2024-01 | Randy W | 2 |
| 2024-02 | Chris H | 7 |
| 2024-02 | Howard Y | 5 |
| 2024-03 | Chris H | 2 |
| 2024-03 | Howard Y | 2 |
| 2024-03 | Randy W | 11 |
| 2024-04 | Howard Y | 7 |
| 2024-04 | Randy W | 3 |
