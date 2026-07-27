# Ride Dispatch API

A Django REST Framework service for managing rides, riders, drivers, and ride
events. It is optimized for **database performance** (no N+1 queries), ships with
**interactive API docs** (drf-spectacular / Swagger UI), and runs fully
containerized on **PostgreSQL + PostGIS**.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Features](#features)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Setup (without Docker)](#local-setup-without-docker)
- [Environment Variables](#environment-variables)
- [Authentication & Authorization](#authentication--authorization)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Project Structure](#project-structure)
- [Design Decisions & Notes](#design-decisions--notes)
- [Known Limitations / Future Work](#known-limitations--future-work)
- [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Layer            | Technology                                  |
| ---------------- | ------------------------------------------- |
| Language         | Python 3.12                                 |
| Framework        | Django 5.1, Django REST Framework 3.15      |
| Database         | PostgreSQL 16 + PostGIS 3.4 (GeoDjango)     |
| Filtering        | `django-filter`                             |
| API Docs         | `drf-spectacular` (OpenAPI 3 + Swagger UI)  |
| DB Driver        | `psycopg2-binary`                           |
| Containerization | Docker + Docker Compose                     |

---

## Features

- **Admin-only ride management** via a DRF `ModelViewSet`.
- **N+1-free list endpoint** using `select_related` for the rider/driver
  foreign keys and a bounded `Prefetch` for ride events.
- **"Today's events" only** — each ride embeds only its `Ride_Event` rows from
  the last 24 hours, keeping payloads small and predictable.
- **Geospatial sorting** — sort rides by proximity to a `lat`/`lon` point using
  a Haversine distance computed in the database.
- **Filtering** by `status` and by rider email.
- **Configurable pagination** (default 20, max 100 per page).
- **Swagger UI** at `/api/docs/`.

---

## Quick Start (Docker)

This is the recommended path. It provisions PostGIS and the API service with a
single command — no local Python or GDAL setup required.

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Build and start the database + api service
docker compose up --build

# 2. In a second terminal, apply migrations
docker compose exec api python manage.py migrate

# 3. Create an admin user (see note below about the `role` field)
docker compose exec api python manage.py createsuperuser
```

Once running:

- API root: <http://localhost:8000/api/>
- Swagger UI: <http://localhost:8000/api/docs/>
- OpenAPI schema: <http://localhost:8000/api/schema/>
- Django admin: <http://localhost:8000/admin/>

> **Important:** The `rides` endpoint is restricted to users whose `role == "admin"`.
> `createsuperuser` sets `role="admin"` automatically (see `UserManager.create_superuser`),
> so a superuser can access everything out of the box.

### Scaling the API service

The `api` service is scale-ready — it has no fixed `container_name`, and its host
ports are published as a range (`8000-8010:8000`), so replicas bind distinct host
ports instead of colliding:

```bash
# Run 3 API replicas (reachable on 8000, 8001, 8002)
docker compose up --scale api=3
```

> For real horizontal scaling in production, front the replicas with a reverse
> proxy / load balancer (e.g. nginx or Traefik) on a single public port and swap
> `runserver` for a WSGI server such as gunicorn (see
> [Known Limitations](#known-limitations--future-work)).

---

## Local Setup (without Docker)

Use this if you want to run the app against a locally installed PostgreSQL/PostGIS.
Note that GeoDjango requires native geospatial libraries (**GDAL, GEOS, PROJ**),
which is the main reason Docker is recommended.

**Prerequisites:**

- Python 3.12
- PostgreSQL 16 with the PostGIS extension
- GDAL / GEOS / PROJ system libraries
  - macOS: `brew install gdal geos proj postgresql`
  - Debian/Ubuntu: `sudo apt-get install binutils libproj-dev gdal-bin libgdal-dev`

```bash
# 1. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create the database and enable PostGIS
createdb dispatch
psql -d dispatch -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 4. Point the app at your local DB (defaults assume Docker; override as needed)
export POSTGRES_HOST=localhost
export POSTGRES_DB=dispatch
export POSTGRES_USER=dispatch
export POSTGRES_PASSWORD=dispatch
export POSTGRES_PORT=5432

# 5. Migrate, create an admin, and run
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Environment Variables

All database configuration is read from the environment, with sensible defaults
for the Docker Compose setup (see `dispatch_api/settings.py`).

| Variable            | Default    | Description                          |
| ------------------- | ---------- | ------------------------------------ |
| `POSTGRES_DB`       | `dispatch` | Database name                        |
| `POSTGRES_USER`     | `dispatch` | Database user                        |
| `POSTGRES_PASSWORD` | `dispatch` | Database password                    |
| `POSTGRES_HOST`     | `db`       | Database host (`db` = compose alias) |
| `POSTGRES_PORT`     | `5432`     | Database port                        |

> **Security note:** `SECRET_KEY`, `DEBUG=True`, and `ALLOWED_HOSTS=["*"]` are
> hard-coded for development convenience. These **must** be moved to environment
> variables and hardened before any production deployment (see
> [Known Limitations](#known-limitations--future-work)).

---

## Authentication & Authorization

- DRF's default authentication classes apply (`SessionAuthentication` and
  `BasicAuthentication`). The simplest way to authenticate during development is
  to log in via the Django admin (`/admin/`) — the browsable API and Swagger UI
  will then use your session.
- **Authorization** is enforced by the custom `IsAdminRole` permission
  (`rides/permissions.py`): a request is allowed only when the user is
  authenticated **and** `user.role == "admin"`.

---

## API Reference

Base path: `/api/`

### Rides

| Method   | Endpoint           | Description               |
| -------- | ------------------ | ------------------------- |
| `GET`    | `/api/rides/`      | List rides (paginated)    |
| `POST`   | `/api/rides/`      | Create a ride             |
| `GET`    | `/api/rides/{id}/` | Retrieve a single ride    |
| `PUT`    | `/api/rides/{id}/` | Replace a ride            |
| `PATCH`  | `/api/rides/{id}/` | Partially update a ride   |
| `DELETE` | `/api/rides/{id}/` | Delete a ride             |

### List query parameters

| Parameter          | Type   | Description                                                                 |
| ------------------ | ------ | --------------------------------------------------------------------------- |
| `status`           | string | Exact-match filter on ride status.                                          |
| `id_rider__email`  | string | Filter rides by the rider's email address.                                  |
| `lat`, `lon`       | float  | Reference point for distance. Both required together. Ranges: lat ∈ [-90, 90], lon ∈ [-180, 180]. |
| `ordering`         | string | Comma-separated. Supports `pickup_time` and `distance` (and `-` prefixes).  |
| `page`             | int    | Page number.                                                                |
| `page_size`        | int    | Items per page (default 20, max 100).                                       |

**Ordering rules:**

- Only `pickup_time` and `distance` are accepted; any other field is ignored.
- Ordering by `distance` **requires** both `lat` and `lon` (otherwise a `400` is
  returned).
- The default ordering is `pickup_time, id_ride` (a stable tiebreaker so page
  boundaries don't shift between requests).

**Example — nearest rides to a point, closest first:**

```bash
curl -u admin@example.com:yourpassword \
  "http://localhost:8000/api/rides/?lat=40.7128&lon=-74.0060&ordering=distance"
```

**Example — filter by status, newest pickups first:**

```bash
curl -u admin@example.com:yourpassword \
  "http://localhost:8000/api/rides/?status=en_route&ordering=-pickup_time"
```

### Example response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id_ride": 1,
      "status": "en_route",
      "rider": {
        "id_user": 2,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "role": "rider",
        "phone_number": ""
      },
      "driver": {
        "id_user": 3,
        "first_name": "Alan",
        "last_name": "Turing",
        "email": "alan@example.com",
        "role": "driver",
        "phone_number": ""
      },
      "pickup_latitude": 40.7128,
      "pickup_longitude": -74.006,
      "dropoff_latitude": 40.73,
      "dropoff_longitude": -73.99,
      "pickup_time": "2026-07-27T12:00:00Z",
      "todays_ride_events": [
        {
          "id_ride_event": 10,
          "description": "status changed to en_route",
          "created_at": "2026-07-27T11:59:00Z"
        }
      ]
    }
  ]
}
```

> `todays_ride_events` contains **only** events created in the last 24 hours.
> Older events are intentionally excluded from the API payload.

---

## Data Model

The schema uses explicit table names and primary key columns (`User`, `Ride`,
`Ride_Event`) to match a fixed database specification.

```
User (table "User")
  ├─ id_user (PK)
  ├─ role, first_name, last_name, email (unique), phone_number
  └─ auth fields: password, is_active, is_staff, is_superuser, ...

Ride (table "Ride")
  ├─ id_ride (PK)
  ├─ status                 (indexed)
  ├─ id_rider  ── FK → User (PROTECT)   related_name="rides_as_rider"
  ├─ id_driver ── FK → User (SET_NULL)  related_name="rides_as_driver", nullable
  ├─ pickup/dropoff latitude & longitude (each indexed)
  └─ pickup_time            (indexed)

Ride_Event (table "Ride_Event")
  ├─ id_ride_event (PK)
  ├─ id_ride ── FK → Ride (CASCADE)     related_name="events"
  ├─ description
  └─ created_at             (indexed, auto_now_add)
```

**Referential integrity choices:**

- `id_rider` uses `on_delete=PROTECT` — a rider with rides cannot be deleted,
  preserving history.
- `id_driver` uses `on_delete=SET_NULL` — if a driver is removed, their rides
  remain but become unassigned.
- `Ride_Event` uses `on_delete=CASCADE` — events are meaningless without their
  parent ride.

---

## Project Structure

```
ride-dispatch-api/
├── dispatch_api/            # Project configuration
│   ├── settings.py          # DB, DRF, drf-spectacular, custom user model
│   ├── urls.py              # Routes: /admin, /api, /api/schema, /api/docs
│   ├── wsgi.py / asgi.py
├── rides/                   # Main application
│   ├── models.py            # User, Ride, Ride_Event
│   ├── serializers.py       # Nested rider/driver + today's events
│   ├── views.py             # RideViewSet (optimized queryset, Haversine sort)
│   ├── permissions.py       # IsAdminRole
│   ├── pagination.py        # StandardResultsSetPagination
│   ├── urls.py              # DRF router → /api/rides/
│   ├── migrations/
│   └── tests.py             # (placeholder — see limitations)
├── Dockerfile               # Python 3.12 + GDAL/PROJ system deps
├── docker-compose.yml       # api + PostGIS services
├── requirements.txt
└── manage.py
```

---

## Design Decisions & Notes

These are the notable choices made during implementation, and the reasoning /
trade-offs behind them.

### 1. Aggressive query optimization on the list endpoint

The list endpoint targets a **2–3 query budget** regardless of page size:

```python
Ride.objects.select_related("id_rider", "id_driver")   # 1 query, joins users
    .prefetch_related(
        Prefetch(
            "events",
            queryset=Ride_Event.objects.filter(created_at__gte=yesterday),
            to_attr="todays_ride_events",                # 1 extra query
        )
    )
```

- `select_related` collapses the rider/driver foreign keys into the main query
  via SQL joins, avoiding a lookup per ride.
- A `Prefetch` with `to_attr` loads *only* the last-24h events in a single extra
  query and attaches them to `ride.todays_ride_events`. The serializer reads that
  attribute directly, so filtering happens **in memory on already-fetched data**
  — no per-ride event queries.
- The all-time `events` reverse relation is deliberately **not** exposed, which
  prevents both N+1 access patterns and unbounded response payloads.

### 2. Haversine distance in SQL, not in Python

Sorting by proximity is done with a raw Haversine expression annotated onto the
queryset:

```python
queryset.annotate(distance=RawSQL(HAVERSINE_SQL, (lat, lon, lat)))
```

- Computing distance in the database means sorting and pagination happen in
  Postgres — we never pull the full table into Python to sort it.
- The formula is parameterized (`%s` placeholders bound to floats), so it is
  **not vulnerable to SQL injection**, and the `lat`/`lon` inputs are validated
  and range-checked before use.

> **Why raw Haversine instead of PostGIS `distance`?** The `Ride` model stores
> pickup coordinates as plain `FloatField`s (per the fixed schema) rather than a
> `PointField`. A spherical Haversine over those floats keeps results accurate
> for ordering without requiring a schema/geometry migration. PostGIS is still
> used as the DB engine, leaving the door open to migrate to a `PointField` +
> spatial index (GiST) later for larger datasets.

### 3. Whitelisted ordering with a stable tiebreaker

Rather than exposing DRF's `OrderingFilter` over all fields, ordering is manually
restricted to `pickup_time` and `distance`. Every ordering appends `id_ride` as a
final tiebreaker so that rows with equal sort keys keep a deterministic order
across paginated requests.

### 4. Explicit table / column names

Models set `db_table` (`"User"`, `"Ride"`, `"Ride_Event"`) and `db_column`
(`id_rider`, `id_driver`, `id_ride`) to conform to a predetermined database
specification instead of Django's auto-generated names. This is intentional and
should be preserved in future migrations.

### 5. Custom email-based User with roles

The project uses a custom `AUTH_USER_MODEL` (`rides.User`) with email as the
`USERNAME_FIELD` and a free-form `role` string. Authorization keys off
`role == "admin"`. `create_superuser` defaults `role` to `"admin"` so that admin
tooling and the API stay in sync.

### Challenges encountered

- **GeoDjango system dependencies.** GDAL/GEOS/PROJ are notoriously fiddly to
  install locally and differ per OS. The Dockerfile bakes them in
  (`binutils`, `libproj-dev`, `gdal-bin`, `libgdal-dev`), which is why Docker is
  the recommended workflow.
- **Bounded nested data.** Embedding *all* ride events would reintroduce N+1s and
  bloat responses. The 24-hour `Prefetch(to_attr=...)` pattern was chosen to keep
  the response both cheap and useful.
- **Keeping distance sorting performant.** Doing the trig in Python would have
  forced full-table scans into memory; pushing it into SQL via `RawSQL` preserves
  the query budget while staying injection-safe.

---

## Known Limitations / Future Work

- **Write path is read-optimized.** The serializer exposes `rider`/`driver` as
  read-only nested objects and does not expose writable `id_rider`/`id_driver`
  fields, so `POST`/`PUT` to create/reassign rides is not fully supported yet.
  Add writable primary-key-related fields (e.g. `PrimaryKeyRelatedField`) to
  enable creation and driver assignment.
- **No test coverage yet.** `rides/tests.py` is a placeholder. High-value tests to
  add: the 2–3 query budget (`assertNumQueries`), the 24h event window,
  `lat`/`lon` validation, ordering rules, and `IsAdminRole` enforcement.
- **Production hardening needed.** Move `SECRET_KEY` to an env var, set
  `DEBUG=False`, restrict `ALLOWED_HOSTS`, and serve via a WSGI server
  (e.g. gunicorn) behind a reverse proxy instead of `runserver`.
- **Consider real geometry.** For large datasets, migrating pickup coordinates to
  a PostGIS `PointField` with a GiST index would outperform the Haversine
  annotation and enable radius/bounding-box queries.
- **Token/JWT auth.** Only session/basic auth is configured. Add token or JWT
  authentication for programmatic clients.

---

## Troubleshooting

- **`403 Forbidden` on `/api/rides/`** — you're either not authenticated or your
  user's `role` isn't `"admin"`. Log in at `/admin/`, or create an admin via
  `createsuperuser`.
- **`400` when ordering by `distance`** — you must supply both `lat` and `lon`.
- **`GDAL`/`GEOS` import errors locally** — install the native geospatial
  libraries (see [Local Setup](#local-setup-without-docker)) or use Docker.
- **DB connection refused** — ensure the `db` service is healthy
  (`docker compose ps`) and that migrations have run.

---

## Running Migrations & Admin (cheat sheet)

```bash
# Docker
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
docker compose exec api python manage.py makemigrations

# Local
python manage.py migrate
python manage.py createsuperuser
```
