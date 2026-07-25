from rest_framework import serializers

from rides.models import Ride, Ride_Event, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id_user",
            "first_name",
            "last_name",
            "email",
            "role",
            "phone_number",
        )


class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ride_Event
        fields = (
            "id_ride_event",
            "description",
            "created_at",
        )


class RideSerializer(serializers.ModelSerializer):
    rider = UserSerializer(source="id_rider", read_only=True)
    driver = UserSerializer(source="id_driver", read_only=True)
    events = RideEventSerializer(many=True, read_only=True)
    # Populated in-memory via Prefetch(to_attr="todays_ride_events") in the ViewSet.
    todays_ride_events = RideEventSerializer(many=True, read_only=True)

    class Meta:
        model = Ride
        fields = (
            "id_ride",
            "status",
            "rider",
            "driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "events",
            "todays_ride_events",
        )
