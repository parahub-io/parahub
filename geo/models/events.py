from django.contrib.gis.db import models
from core.models import ULIDModel
from identity.models import Profile
from taxonomy.models import Category
from .establishments import WorldObject


class Event(ULIDModel):
    """Community event/meetup."""

    class EventType(models.TextChoices):
        OFFLINE = 'OFFLINE', 'Offline (in-person)'
        ONLINE = 'ONLINE', 'Online (virtual)'
        HYBRID = 'HYBRID', 'Hybrid (both)'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    # Organizer
    organizer = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="organized_events",
                                  help_text="Profile that created this event")
    establishment = models.ForeignKey(
        'Establishment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='organized_events',
        help_text="If set, event is posted on behalf of this establishment"
    )

    # Basic info
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="events", help_text="Event category from taxonomy")
    event_type = models.CharField(max_length=10, choices=EventType.choices, default=EventType.OFFLINE)

    # Timing
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='UTC', help_text="IANA timezone (e.g., Europe/Moscow)")

    # Location (offline/hybrid) - either building OR arbitrary point
    world_object = models.ForeignKey(WorldObject, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='events')
    location = models.PointField(srid=4326, geography=True, null=True, blank=True,
                                 help_text="Location if not in a building (park, outdoor venue)")
    location_name = models.CharField(max_length=255, blank=True,
                                     help_text="Human-readable location description")

    # Online info (online/hybrid)
    online_url = models.URLField(blank=True, help_text="Jitsi/Zoom/Google Meet link")

    # Capacity
    max_participants = models.PositiveIntegerField(null=True, blank=True,
                                                   help_text="Maximum participants (null = unlimited)")

    # Matrix chat room
    matrix_room_id = models.CharField(max_length=255, blank=True, db_index=True,
                                      help_text="Matrix room ID for event chat")

    # Media
    cover_image = models.ImageField(upload_to='events/%Y/%m/', blank=True,
                                     help_text="Uploaded cover image")
    cover_image_url = models.URLField(blank=True, help_text="External cover image URL (fallback)")

    # Status
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)

    # Stats (denormalized for performance)
    participants_count = models.PositiveIntegerField(default=0, help_text="Number of confirmed participants")
    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'starts_at']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['organizer', 'status']),
        ]
        ordering = ['starts_at']

    def __str__(self):
        return f"{self.title} ({self.starts_at.strftime('%Y-%m-%d %H:%M')})"

    def get_location_display(self):
        """Return human-readable location string."""
        if self.world_object:
            return self.world_object.full_address
        elif self.location_name:
            return self.location_name
        elif self.location:
            return f"{self.location.y:.6f}, {self.location.x:.6f}"
        return ""

    def is_full(self):
        """Check if event has reached max participants."""
        if self.max_participants is None:
            return False
        return self.participants_count >= self.max_participants

class EventParticipant(ULIDModel):
    """Event registration/participation."""

    class ParticipantStatus(models.TextChoices):
        GOING = 'GOING', 'Going'
        MAYBE = 'MAYBE', 'Maybe'
        CANCELLED = 'CANCELLED', 'Cancelled'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="event_participants")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="event_participations")
    status = models.CharField(max_length=15, choices=ParticipantStatus.choices, default=ParticipantStatus.GOING)

    # Track when they joined Matrix room (for cleanup if needed)
    joined_matrix_room = models.BooleanField(default=False)

    class Meta:
        unique_together = ('event', 'profile')
        indexes = [
            models.Index(fields=['event', 'status']),
            models.Index(fields=['profile', 'status']),
        ]

    def __str__(self):
        return f"{self.profile} -> {self.event.title} ({self.status})"
