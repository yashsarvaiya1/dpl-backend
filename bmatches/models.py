# bmatches/models.py

from django.db import models
from django.utils import timezone
from django.conf import settings
from matches.models import Match, MatchPosition, Player


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class BMatch(models.Model):
    STATUS_UPCOMING = 'upcoming'
    STATUS_ACTIVE = 'active'
    STATUS_CLOSED = 'closed'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_UPCOMING, 'Upcoming'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CLOSED, 'Closed'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name='bmatches',
        null=True, blank=True
    )
    ticket_amount = models.IntegerField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UPCOMING,
        null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_bmatches'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return f"BMatch {self.id} - {self.match} [{self.status}]"


class BMatchPosition(models.Model):
    bmatch = models.ForeignKey(
        BMatch,
        on_delete=models.CASCADE,
        related_name='positions',
        null=True, blank=True
    )
    position_label = models.CharField(max_length=20, null=True, blank=True)
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bmatch_positions'
    )
    score = models.IntegerField(null=True, blank=True)
    is_no_player = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('bmatch', 'position_label')

    def __str__(self):
        return f"{self.bmatch} - {self.position_label}"


class BRoom(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ONGOING = 'ongoing'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ONGOING, 'Ongoing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    bmatch = models.ForeignKey(
        BMatch,
        on_delete=models.CASCADE,
        related_name='rooms',
        null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BRoom {self.id} - {self.bmatch} [{self.status}]"

    @property
    def entry_count(self):
        return self.entries.count()

    @property
    def is_full(self):
        return self.entries.count() >= 10


class BRoomEntry(models.Model):
    broom = models.ForeignKey(
        BRoom,
        on_delete=models.CASCADE,
        related_name='entries',
        null=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='broom_entries',
        null=True, blank=True
    )
    box_value = models.CharField(max_length=20, null=True, blank=True)
    # e.g. kkr-1, csk-3
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('broom', 'user')

    def __str__(self):
        return f"{self.user} in BRoom {self.broom_id} → {self.box_value}"


class TicketTransaction(models.Model):
    TYPE_CREDIT = 'credit'
    TYPE_DEBIT = 'debit'

    TYPE_CHOICES = [
        (TYPE_CREDIT, 'Credit'),
        (TYPE_DEBIT, 'Debit'),
    ]

    REASON_ADMIN_ADD = 'admin_add'
    REASON_ADMIN_REMOVE = 'admin_remove'
    REASON_BOX_OPEN = 'box_open'
    REASON_WIN_REWARD = 'win_reward'
    REASON_REFUND = 'refund'

    REASON_CHOICES = [
        (REASON_ADMIN_ADD, 'Admin Add'),
        (REASON_ADMIN_REMOVE, 'Admin Remove'),
        (REASON_BOX_OPEN, 'Box Open'),
        (REASON_WIN_REWARD, 'Win Reward'),
        (REASON_REFUND, 'Refund'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ticket_transactions',
        null=True, blank=True
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        null=True, blank=True
    )
    amount = models.IntegerField(null=True, blank=True)
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        null=True, blank=True
    )
    reference_bmatch = models.ForeignKey(
        BMatch,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions'
    )
    reference_broom = models.ForeignKey(
        BRoom,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.user} - {self.transaction_type} {self.amount} [{self.reason}]"
