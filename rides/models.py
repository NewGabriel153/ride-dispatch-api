from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id_user = models.AutoField(primary_key=True)
    role = models.CharField(max_length=50)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "User"

    def __str__(self) -> str:
        return self.email


class Ride(models.Model):
    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(max_length=50, db_index=True)
    id_rider = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        db_column="id_rider",
        related_name="rides_as_rider",
    )
    id_driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_driver",
        related_name="rides_as_driver",
    )
    pickup_latitude = models.FloatField(db_index=True)
    pickup_longitude = models.FloatField(db_index=True)
    dropoff_latitude = models.FloatField(db_index=True)
    dropoff_longitude = models.FloatField(db_index=True)
    pickup_time = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "Ride"

    def __str__(self) -> str:
        return f"Ride {self.id_ride} ({self.status})"


class Ride_Event(models.Model):
    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        db_column="id_ride",
        related_name="events",
    )
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "Ride_Event"

    def __str__(self) -> str:
        return f"Event {self.id_ride_event} for Ride {self.id_ride_id}"
