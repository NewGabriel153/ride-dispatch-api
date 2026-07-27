from datetime import timedelta

from django.db.models import Prefetch, QuerySet
from django.db.models.expressions import RawSQL
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from rides.models import Ride, Ride_Event
from rides.pagination import StandardResultsSetPagination
from rides.permissions import IsAdminRole
from rides.serializers import RideSerializer

# Haversine distance (km) between a request lat/lon and the ride pickup point.
# Executed in PostgreSQL so sorting does not pull rows into Python.
# Params: (lat, lon, lat) — lat appears twice for the spherical-law formula.
HAVERSINE_SQL = """
(
    6371 * acos(
        cos(radians(%s)) * cos(radians(pickup_latitude))
        * cos(radians(pickup_longitude) - radians(%s))
        + sin(radians(%s)) * sin(radians(pickup_latitude))
    )
)
"""


class RideViewSet(viewsets.ModelViewSet):
    """
    Admin-only CRUD for rides.

    Query budget for list (target 2–3 queries):
      1. Paginated Ride rows with rider/driver joined via select_related
      2. Prefetched Ride_Event rows limited to the last 24 hours
      3. Optional COUNT(*) for PageNumberPagination
    """

    serializer_class = RideSerializer
    permission_classes = [IsAdminRole]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "id_rider__email"]

    def get_queryset(self) -> QuerySet[Ride]:
        # Window start for "today's" events — never load the full event history.
        yesterday = timezone.now() - timedelta(days=1)

        queryset: QuerySet[Ride] = (
            Ride.objects.select_related("id_rider", "id_driver")
            .prefetch_related(
                Prefetch(
                    # related_name on Ride_Event.id_ride is "events"
                    "events",
                    queryset=Ride_Event.objects.filter(created_at__gte=yesterday),
                    to_attr="todays_ride_events",
                )
            )
        )

        # Optional geographic distance annotation for sorting near a point.
        lat_param = self.request.query_params.get("lat")
        lon_param = self.request.query_params.get("lon")
        has_distance = False

        if lat_param is not None and lon_param is not None:
            try:
                lat = float(lat_param)
                lon = float(lon_param)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {"detail": "Query params 'lat' and 'lon' must be valid floats."}
                ) from exc

            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                raise ValidationError(
                    {
                        "detail": (
                            "'lat' must be in [-90, 90] and "
                            "'lon' must be in [-180, 180]."
                        )
                    }
                )

            queryset = queryset.annotate(
                distance=RawSQL(HAVERSINE_SQL, (lat, lon, lat))
            )
            has_distance = True

        # Stable ordering so page boundaries do not shift between requests.
        ordering_param = self.request.query_params.get("ordering", "")
        order_fields = [field.strip() for field in ordering_param.split(",") if field.strip()]

        applied: list[str] = []
        for field in order_fields:
            descending = field.startswith("-")
            name = field.lstrip("-")

            if name == "distance":
                if not has_distance:
                    raise ValidationError(
                        {
                            "detail": (
                                "Ordering by 'distance' requires both "
                                "'lat' and 'lon' query parameters."
                            )
                        }
                    )
                applied.append(f"-distance" if descending else "distance")
            elif name == "pickup_time":
                applied.append(f"-pickup_time" if descending else "pickup_time")

        if applied:
            queryset = queryset.order_by(*applied, "id_ride")
        else:
            queryset = queryset.order_by("pickup_time", "id_ride")

        return queryset
