from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.models import ULIDModel

User = get_user_model()


class PushSubscription(ULIDModel):
    """
    Web Push subscription for browser notifications.
    Stores subscription info for sending push notifications via Web Push API.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='push_subscriptions',
        help_text='User who owns this push subscription'
    )

    # Push subscription endpoint (unique per browser/device)
    endpoint = models.URLField(
        max_length=500,
        unique=True,
        help_text='Push service endpoint URL'
    )

    # Subscription keys (JSON format from browser PushSubscription)
    p256dh = models.CharField(
        max_length=200,
        help_text='Client public key for encryption (p256dh)'
    )

    auth = models.CharField(
        max_length=200,
        help_text='Authentication secret'
    )

    # User agent for debugging
    user_agent = models.TextField(
        blank=True,
        help_text='Browser user agent string'
    )

    # Tracking
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this subscription is active'
    )

    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time a notification was sent to this subscription'
    )

    failed_count = models.IntegerField(
        default=0,
        help_text='Number of failed delivery attempts'
    )

    class Meta:
        db_table = 'push_subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['endpoint']),
        ]

    def __str__(self):
        return f"Push subscription for {self.user.email} ({self.endpoint[:50]}...)"

    def mark_failed(self):
        """Increment failed count and deactivate if too many failures"""
        self.failed_count += 1
        if self.failed_count >= 3:
            self.is_active = False
        self.save(update_fields=['failed_count', 'is_active'])

    def mark_success(self):
        """Reset failed count on successful delivery"""
        from django.utils import timezone
        self.failed_count = 0
        self.last_sent_at = timezone.now()
        self.save(update_fields=['failed_count', 'last_sent_at'])


class FCMDevice(ULIDModel):
    """
    FCM device token for native push notifications (Capacitor Android/iOS).
    Separate from PushSubscription (Web Push VAPID).
    """
    class Platform(models.TextChoices):
        ANDROID = 'android', 'Android'
        IOS = 'ios', 'iOS'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='fcm_devices',
    )
    token = models.TextField(unique=True, help_text="FCM registration token")
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.ANDROID)
    is_active = models.BooleanField(default=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    failed_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'fcm_devices'
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"FCM {self.platform} for {self.user.username}"

    def mark_failed(self):
        self.failed_count += 1
        if self.failed_count >= 3:
            self.is_active = False
        self.save(update_fields=['failed_count', 'is_active'])

    def mark_success(self):
        from django.utils import timezone
        self.failed_count = 0
        self.last_sent_at = timezone.now()
        self.save(update_fields=['failed_count', 'last_sent_at'])


class Notification(ULIDModel):
    """
    Persistent in-app notification — the source of truth for the notification
    feed and the unread badge.

    Every alert produced by ``notifications.services.emit_notification`` lands
    here (history is kept indefinitely) before being fanned out to the live WS
    channel + Web Push + FCM. ``read_at IS NULL`` means unread.
    """
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='Account that receives this notification',
    )

    # Matches the keys in services._should_notify TYPE_TO_CATEGORY
    type = models.CharField(max_length=50, help_text='Event type, e.g. new_booking')
    category = models.CharField(
        max_length=30, blank=True,
        help_text='Preference category (social/contracts/governance/calls/rental/…)',
    )

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True, help_text='Deep link opened on click')

    data = models.JSONField(
        default=dict, blank=True,
        help_text='Structured payload (object ids, actor name, …)',
    )

    read_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='When the recipient marked it read; NULL = unread',
    )

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'read_at']),
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'category']),
        ]

    def __str__(self):
        state = 'unread' if self.read_at is None else 'read'
        return f"Notification[{self.type}] to {self.recipient_id} ({state})"


class Activity(ULIDModel):
    """
    Append-only log of the actor's OWN first-class actions (voted, verified,
    listed an item, created a contract, …).

    Distinct from ``Notification`` on purpose — different lifecycles:

    - ``Notification`` is *incoming* (things others do to you), has mutable
      ``read_at`` state, is gated by per-category prefs, and drives the bell
      badge.
    - ``Activity`` is *outgoing* (things you do), immutable, always logged, and
      **never counts as unread** — the bell badge ignores it.

    It is an *index over* the canonical objects: ``content_type`` + ``object_id``
    point back to the real row (PollVote / Verification / Item / Contract), so the
    truth lives there, not here. The GenericFK (unlike a real FK) does not cascade,
    so the log row survives deletion of its source — correct for an append-only
    log ("you signed contract X" stays even if X is later removed).

    Written from ``notifications.signals`` (post_save on the source models), so the
    row is born in the same transaction as the action — one choke point, no
    scattered emit calls, no drift. Pushed live to the actor's ``user:{id}`` WS
    channel (cross-device visibility + tamper-watch). OTS anchoring is deferred.
    """
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activities',
        help_text='Account that performed the action',
    )

    verb = models.CharField(max_length=50, help_text='Action type, e.g. voted, verified, listed_item')
    category = models.CharField(
        max_length=30, blank=True,
        help_text='Feed category for icon/grouping (governance/social/market/contracts/…)',
    )

    # Pointer to the canonical object. GenericFK does NOT cascade on object delete,
    # so the log entry survives — append-only by design.
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.CharField(max_length=26, blank=True, default='')
    content_object = GenericForeignKey('content_type', 'object_id')

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True, help_text='Deep link to the source object')

    data = models.JSONField(
        default=dict, blank=True,
        help_text='Structured payload (object ids, …)',
    )

    class Meta:
        db_table = 'activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['actor', 'category']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Activity[{self.verb}] by {self.actor_id}"
