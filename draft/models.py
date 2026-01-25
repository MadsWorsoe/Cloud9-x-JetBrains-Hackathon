import uuid
from django.db import models
from matches.models import Game
from matches.models import Team

class Champion(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # GraphQL UUID
    name = models.CharField(max_length=128)

    def __str__(self):
        return self.name

class DraftAction(models.Model):
    game = models.ForeignKey(
        Game,
        on_delete=models.PROTECT,
        related_name="draft_actions"
    )

    sequence_number = models.PositiveSmallIntegerField()

    action_type = models.CharField(
        max_length=4,
        choices=[("pick", "Pick"), ("ban", "Ban")]
    )

    team_side = models.CharField(
        max_length=4,
        choices=[("blue", "Blue"), ("red", "Red")]
    )

    champion = models.ForeignKey(
        Champion,
        on_delete=models.PROTECT
    )

    # Optional: store raw drafter ID if needed
    drafter_id = models.CharField(max_length=16, null=True, blank=True)

    class Meta:
        ordering = ["sequence_number"]
        unique_together = ("game", "sequence_number")

    def __str__(self):
        return f"{self.action_type.title()} {self.champion.name} by {self.team_side} in Game {self.game.game_id}"


class TeamChampionPickStats(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    champion = models.ForeignKey(Champion,on_delete=models.PROTECT)

    wins = models.PositiveIntegerField(default=0)
    games_played = models.PositiveIntegerField(default=0)

    red_side_wins = models.PositiveIntegerField(default=0)
    red_side_games = models.PositiveIntegerField(default=0)
    blue_side_wins = models.PositiveIntegerField(default=0)
    blue_side_games = models.PositiveIntegerField(default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("team", "champion")
        indexes = [
            models.Index(fields=["team", "champion"]),
        ]

class TeamChampionBanStats(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    champion = models.ForeignKey(Champion,on_delete=models.PROTECT)

    games_banned = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)

    total_self_bans = models.PositiveIntegerField(default=0)
    blue_side_self_bans = models.PositiveIntegerField(default=0)
    blue_side_self_wins = models.PositiveIntegerField(default=0)

    red_side_self_bans = models.PositiveIntegerField(default=0)
    red_side_self_wins = models.PositiveIntegerField(default=0)

    total_opponent_bans = models.PositiveIntegerField(default=0)

    red_side_opponent_bans = models.PositiveIntegerField(default=0)
    red_side_opponent_wins = models.PositiveIntegerField(default=0)

    blue_side_opponent_bans = models.PositiveIntegerField(default=0)
    blue_side_opponent_wins = models.PositiveIntegerField(default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("team", "champion")
        indexes = [
            models.Index(fields=["team", "champion"]),
        ]

class DraftSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Core state
    blue_team = models.CharField(max_length=128, null=True, blank=True)
    red_team = models.CharField(max_length=128, null=True, blank=True)

    # Draft data
    picks = models.JSONField(default=dict)
    bans = models.JSONField(default=dict)

    # Optional
    status = models.CharField(
        max_length=32,
        default="IN_PROGRESS",
        choices=[
            ("IN_PROGRESS", "In progress"),
            ("COMPLETED", "Completed"),
        ],
    )

    def __str__(self):
        return f"Draft {self.id}"