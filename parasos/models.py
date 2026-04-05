"""
ParaSOS — Neighborhood emergency mutual aid system.

Two types of participants:
- LOCAL: neighbors who can physically respond (2-5 min)
- REMOTE: family members who coordinate remotely (call 112, share medical context)

Three alert levels:
- INFO: suspicious activity (no sound, quiet push)
- WARNING: alarm triggered, door knocked at night (short sound)
- EMERGENCY: need help NOW — intrusion, fire, medical (siren + repeat push)
"""

import secrets

from django.contrib.gis.db import models as gis_models
from django.db import models
from core.models import ULIDModel
from identity.models import Profile


def _generate_invite_token():
    return secrets.token_urlsafe(16)


class SafetyGroup(ULIDModel):
    """Neighborhood safety group with geographic coverage."""

    class Visibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public (discoverable in Nearby)'
        PRIVATE = 'PRIVATE', 'Private (invite-only)'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC,
    )

    # Creator / admin
    created_by = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='created_safety_groups',
    )

    # Geographic coverage — null for location-free groups (friends/family)
    center = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)
    radius_m = models.PositiveIntegerField(
        null=True, blank=True,
        default=1000,
        help_text="Coverage radius in meters",
    )

    world_object = models.ForeignKey(
        'geo.WorldObject', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='safety_groups',
    )

    # Matrix chat room (auto-created)
    matrix_room_id = models.CharField(max_length=255, blank=True, db_index=True)

    # Settings
    is_active = models.BooleanField(default=True)
    quiet_hours_start = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Hour (0-23) when INFO alerts are suppressed",
    )
    quiet_hours_end = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Hour (0-23) when INFO suppression ends",
    )

    max_members = models.PositiveIntegerField(
        default=50,
        help_text="Maximum group members (0 = unlimited)",
    )

    # Denormalized
    members_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return self.name


class SafetyGroupMember(ULIDModel):
    """Membership in a safety group."""

    class Role(models.TextChoices):
        MEMBER = 'MEMBER', 'Member'
        ADMIN = 'ADMIN', 'Admin'

    class Presence(models.TextChoices):
        LOCAL = 'LOCAL', 'Local (can physically respond)'
        REMOTE = 'REMOTE', 'Remote (coordinates remotely)'

    group = models.ForeignKey(
        SafetyGroup, on_delete=models.CASCADE,
        related_name='members',
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='safety_memberships',
    )

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    presence = models.CharField(max_length=10, choices=Presence.choices, default=Presence.LOCAL)

    # Notification preferences
    notify_info = models.BooleanField(default=False)
    notify_warning = models.BooleanField(default=True)
    notify_emergency = models.BooleanField(default=True)
    quiet_hours_override = models.BooleanField(
        default=False,
        help_text="Ignore group quiet hours for this member",
    )

    # Emergency context (visible only during active SOS)
    emergency_context = models.TextField(
        blank=True,
        help_text="Medical info, allergies, doctor contacts — shown only during active SOS",
    )

    # Matrix room tracking
    joined_matrix_room = models.BooleanField(default=False)

    class Meta:
        unique_together = ('group', 'profile')
        indexes = [
            models.Index(fields=['group', 'role']),
            models.Index(fields=['profile']),
        ]

    def __str__(self):
        return f"{self.profile} in {self.group} ({self.presence})"


class SOSAlert(ULIDModel):
    """Emergency alert sent to a safety group."""

    class Level(models.TextChoices):
        INFO = 'INFO', 'Info (suspicious activity)'
        WARNING = 'WARNING', 'Warning (alarm triggered)'
        EMERGENCY = 'EMERGENCY', 'Emergency (need help NOW)'

    class Category(models.TextChoices):
        SUSPICIOUS_ACTIVITY = 'SUSPICIOUS_ACTIVITY', 'Suspicious activity'
        ALARM_TRIGGERED = 'ALARM_TRIGGERED', 'Alarm triggered'
        MEDICAL = 'MEDICAL', 'Medical emergency'
        FIRE = 'FIRE', 'Fire'
        INTRUSION = 'INTRUSION', 'Intrusion / break-in'
        OTHER = 'OTHER', 'Other'

    class Source(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual (SOS button)'
        IOT_SENSOR = 'IOT_SENSOR', 'IoT sensor'
        HA_AUTOMATION = 'HA_AUTOMATION', 'Home Assistant automation'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        RESOLVED = 'RESOLVED', 'Resolved'
        FALSE_ALARM = 'FALSE_ALARM', 'False alarm'

    group = models.ForeignKey(
        SafetyGroup, on_delete=models.CASCADE,
        related_name='alerts',
    )
    sender = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='sent_sos_alerts',
    )

    level = models.CharField(max_length=15, choices=Level.choices)
    category = models.CharField(max_length=25, choices=Category.choices, default=Category.OTHER)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)

    message = models.TextField(blank=True, help_text="Optional text message")
    location = gis_models.PointField(
        srid=4326, geography=True,
        null=True, blank=True,
        help_text="Sender's location at time of SOS",
    )

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        Profile, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='resolved_sos_alerts',
    )

    # Denormalized response stats
    seen_count = models.PositiveIntegerField(default=0)
    responding_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['group', 'status', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"SOS [{self.level}] in {self.group} by {self.sender}"


class SOSResponse(ULIDModel):
    """Response to an SOS alert from a group member."""

    class Status(models.TextChoices):
        SEEN = 'SEEN', 'Seen'
        ON_WAY = 'ON_WAY', 'On the way'
        ON_SITE = 'ON_SITE', 'On site'
        UNABLE = 'UNABLE', 'Unable to respond'

    alert = models.ForeignKey(
        SOSAlert, on_delete=models.CASCADE,
        related_name='responses',
    )
    responder = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='sos_responses',
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SEEN)
    note = models.TextField(blank=True, help_text="What responder sees / situation report")

    class Meta:
        unique_together = ('alert', 'responder')
        indexes = [
            models.Index(fields=['alert', 'status']),
        ]

    def __str__(self):
        return f"{self.responder} -> {self.alert} ({self.status})"


class InactivityWatch(ULIDModel):
    """
    Passive safety monitor for elderly / vulnerable people.
    Triggers WARNING alert when no activity detected for max_inactivity_hours.
    Activity tracked via IoT sensors or HA entities.
    """

    group = models.ForeignKey(
        SafetyGroup, on_delete=models.CASCADE,
        related_name='inactivity_watches',
    )
    watched_profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='inactivity_watches',
        help_text="Person being monitored",
    )

    # Who gets notified (usually family)
    watchers = models.ManyToManyField(
        Profile, blank=True,
        related_name='watching_inactivity',
        help_text="Profiles notified on inactivity (family members)",
    )

    # IoT/HA data sources
    ha_home = models.ForeignKey(
        'iot.HAHome', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inactivity_watches',
    )
    iot_devices = models.ManyToManyField(
        'iot.IoTDevice', blank=True,
        related_name='inactivity_watches',
        help_text="Sensors that count as activity (motion, door, fridge)",
    )

    # Thresholds
    max_inactivity_hours = models.PositiveIntegerField(
        default=12,
        help_text="Hours without activity before triggering alert",
    )
    check_start_hour = models.PositiveSmallIntegerField(
        default=8,
        help_text="Don't check before this hour (0-23)",
    )
    check_end_hour = models.PositiveSmallIntegerField(
        default=22,
        help_text="Don't check after this hour (0-23)",
    )

    # State
    last_activity_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Last detected activity timestamp (updated by IoT/HA events)",
    )
    last_alert_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When last inactivity alert was sent (avoid spam)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Pause monitoring (e.g. person is traveling)",
    )

    class Meta:
        unique_together = ('group', 'watched_profile')
        indexes = [
            models.Index(fields=['is_active', 'last_activity_at']),
        ]

    def __str__(self):
        return f"InactivityWatch: {self.watched_profile} in {self.group}"


class GroupInvite(ULIDModel):
    """Invite link for joining a safety group (especially PRIVATE ones)."""

    group = models.ForeignKey(
        SafetyGroup, on_delete=models.CASCADE,
        related_name='invites',
    )
    created_by = models.ForeignKey(
        Profile, on_delete=models.CASCADE,
        related_name='created_group_invites',
    )
    token = models.CharField(
        max_length=32, unique=True, default=_generate_invite_token,
        db_index=True,
    )
    label = models.CharField(max_length=100, blank=True, help_text="Optional label (e.g. 'for family')")
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['group', 'is_active']),
        ]

    def __str__(self):
        return f"Invite {self.token[:8]}… for {self.group}"

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        if self.expires_at:
            from django.utils import timezone
            if timezone.now() > self.expires_at:
                return False
        return True
