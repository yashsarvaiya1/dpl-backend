# matches/models.py

from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Team(models.Model):
    name = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.name or ''


class Player(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='players',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    def __str__(self):
        return self.name or ''


class Match(models.Model):
    team_1 = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='matches_as_team1',
        null=True,
        blank=True
    )
    team_2 = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='matches_as_team2',
        null=True,
        blank=True
    )
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.team_1} vs {self.team_2} on {self.date}"


class MatchPosition(models.Model):
    POSITION_CHOICES = [
        ('team1_1', 'Team1 Position 1'),
        ('team1_2', 'Team1 Position 2'),
        ('team1_3', 'Team1 Position 3'),
        ('team1_4', 'Team1 Position 4'),
        ('team1_5', 'Team1 Position 5'),
        ('team2_1', 'Team2 Position 1'),
        ('team2_2', 'Team2 Position 2'),
        ('team2_3', 'Team2 Position 3'),
        ('team2_4', 'Team2 Position 4'),
        ('team2_5', 'Team2 Position 5'),
    ]

    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name='positions',
        null=True,
        blank=True
    )
    position_label = models.CharField(max_length=20, null=True, blank=True)
    # e.g. kkr-1, csk-3 — set at creation using team slugs
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='match_positions'
    )
    score = models.IntegerField(null=True, blank=True)
    is_no_player = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('match', 'position_label')

    def __str__(self):
        return f"{self.match} - {self.position_label}"
