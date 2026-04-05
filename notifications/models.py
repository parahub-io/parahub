from django.db import models
from django.contrib.auth import get_user_model
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
