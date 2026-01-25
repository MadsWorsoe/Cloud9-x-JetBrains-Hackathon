from datetime import datetime

from django.db import models

class Team(models.Model):
    external_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    slug = models.SlugField(unique=True, null=True, blank=True)
    logo_url = models.URLField(blank=True, null=True)
    color_primary = models.CharField(max_length=20, blank=True, null=True)
    color_secondary = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.name or self.external_id

class Player(models.Model):
    external_id = models.CharField(max_length=128, null=True)
    name = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="players")
    role = models.CharField(max_length=128, null = True, blank = True)
    role_id = models.SmallIntegerField(null = True, blank = True)

    def __str__(self):
        return self.name or self.external_id

class Match(models.Model):
    external_id = models.CharField(max_length=128, unique=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    last_processed_at = models.DateTimeField(null=True, blank=True)
    team_1 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="team_1")
    team_2 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="team_2")
    team_1_score = models.SmallIntegerField(null=True, blank=True)
    team_2_score = models.SmallIntegerField(null=True, blank=True)
    winning_team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="match_winning_team")
    tournament = models.CharField(max_length=255, null=True, blank=True, default="Worlds")

    STATES = [
        ('UPCOMING', 'UPCOMING'),
        ('STARTED', 'STARTED'),
        ('FINISHED', 'FINISHED'),
        ('PROCESSING', 'PROCESSING'),
        ('PROCESSED', 'PROCESSED'),
        ('MIGRATING', 'MIGRATING'),
        ('MIGRATED', 'MIGRATED'),
        ('SERIES_FETCHED_FOR_DRAFT', 'SERIES_FETCHED_FOR_DRAFT'),
        ('DRAFT_ACTIONS_FETCHED', 'DRAFT_ACTIONS_FETCHED'),
        ('DRAFT_SERIES_STATE_EMPTY', 'DRAFT_SERIES_STATE_EMPTY'),
    ]

    state = models.CharField(max_length=100, choices=STATES, default='UPCOMING')

    class Meta:
        indexes = [
            models.Index(fields=['tournament', 'winning_team']),  # For matches_view and teams_view filters
            models.Index(fields=['winning_team', 'tournament']),  # Alternative order for different query patterns
            models.Index(fields=['team_1', 'team_2']),  # For team analysis queries
            models.Index(fields=['-id']),  # For matches_view order_by('-id')
        ]


    def __str__(self):
        return self.external_id

class Game(models.Model):
    match = models.ForeignKey(Match, on_delete=models.SET_NULL, null=True, related_name="games")
    team_1 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="team_1_game")
    team_2 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="team_2_game")
    game_id = models.SmallIntegerField(null=True, blank=True)
    winning_team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="game_winning_team")

    class Meta:
        indexes = [
            models.Index(fields=['team_1', 'team_2']),  # For team_analysis Game queries
            models.Index(fields=['match', 'game_id']),  # For match_frontend_demo queries
            models.Index(fields=['winning_team']),  # For teams_view win calculations
        ]


    team_1_score = models.SmallIntegerField(null=True, blank=True)
    team_2_score = models.SmallIntegerField(null=True, blank=True)
    team_1_side = models.CharField(max_length=10, null=True, blank=True)
    team_2_side = models.CharField(max_length=10, null=True, blank=True)

    team_1_top_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_1_jungle_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_1_mid_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_1_bot_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_1_support_player_name = models.CharField(max_length=255, null=True, blank=True)

    team_2_top_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_2_jungle_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_2_mid_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_2_bot_player_name = models.CharField(max_length=255, null=True, blank=True)
    team_2_support_player_name = models.CharField(max_length=255, null=True, blank=True)

    team_1_top_champion = models.CharField(max_length=128, null=True, blank=True)
    team_1_jungle_champion = models.CharField(max_length=128, null=True, blank=True)
    team_1_mid_champion = models.CharField(max_length=128, null=True, blank=True)
    team_1_bot_champion = models.CharField(max_length=128, null=True, blank=True)
    team_1_support_champion = models.CharField(max_length=128, null=True, blank=True)

    team_2_top_champion = models.CharField(max_length=128, null=True, blank=True)
    team_2_jungle_champion = models.CharField(max_length=128, null=True, blank=True)
    team_2_mid_champion = models.CharField(max_length=128, null=True, blank=True)
    team_2_bot_champion = models.CharField(max_length=128, null=True, blank=True)
    team_2_support_champion = models.CharField(max_length=128, null=True, blank=True)

class Frame(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="frames")
    updated_at = models.DateTimeField(db_index=True)
    raw_payload = models.JSONField()

    class Meta:
        unique_together = (("match", "updated_at"),)
        
class Event(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    occured_at = models.DateTimeField(db_index=True)
    event_data = models.JSONField()
    
class PlayerFrames(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="playerFrames")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="frames")

    game_id = models.SmallIntegerField()
    game_time = models.SmallIntegerField()

    position_x = models.IntegerField()
    position_y = models.IntegerField()

    vision_score = models.FloatField()
    kills = models.SmallIntegerField()
    deaths = models.SmallIntegerField()
    gold = models.IntegerField()
    experience = models.IntegerField(default=-1)
    is_alive = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['match', 'game_id']),  # For match_frontend_demo
            models.Index(fields=['match', 'game_id', 'game_time']),  # For time-based filtering
            models.Index(fields=['player', 'game_time']),  # For player_view
            models.Index(fields=['game_time']),  # For time range filtering
        ]


class PlayerEvents(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="playerEvents")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="events")

    game_id = models.SmallIntegerField(null=True, blank=True)
    game_time = models.SmallIntegerField(null=True, blank=True)

    position_x = models.IntegerField(null=True, blank=True)
    position_y = models.IntegerField(null=True, blank=True)

    event_name = models.CharField(max_length=128, null=True, blank=True)
    event_type = models.CharField(max_length=128, null=True, blank=True)
    event_action = models.CharField(max_length=128, null=True, blank=True)
    event_data = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['event_name', 'player']),  # For ward queries in team_analysis
            models.Index(fields=['match', 'game_id', 'event_name']),  # For match_frontend_demo wards
            models.Index(fields=['player', 'event_name']),  # For player_view
            models.Index(fields=['game_time']),  # For time-based ordering
        ]


class MatchWorkerJob(models.Model):
    """
    Tracks individual worker jobs for a match.
    Includes status/state, timestamps, and error logging.
    """

    # Worker types
    WORKER_TYPES = [
        ("websocket", "Websocket Worker"),
        ("live_series", "Live Series Worker"),
        ("analyse", "Analyse Worker"),
    ]

    # Job states
    STATES = [
        ("PENDING", "Pending"),
        ("STARTED", "Started"),
        ("FINISHED", "Finished"),
        ("ERROR", "Error"),
    ]

    # Foreign key to the Match
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="worker_jobs"
    )

    # Type of worker (websocket, live_series, analyse)
    worker_type = models.CharField(max_length=20, choices=WORKER_TYPES)

    # Job state
    state = models.CharField(max_length=20, choices=STATES, default="PENDING")

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Optional error message
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("match", "worker_type")
        ordering = ["match", "worker_type"]

    def __str__(self):
        return f"{self.match.external_id} - {self.worker_type} [{self.state}]"

    # Convenience methods for updating state
    def mark_started(self):
        self.state = "STARTED"
        self.started_at = datetime.now()
        self.save(update_fields=["state", "started_at"])

    def mark_finished(self):
        self.state = "FINISHED"
        self.finished_at = datetime.now()
        self.save(update_fields=["state", "finished_at"])

    def mark_error(self, msg=""):
        self.state = "ERROR"
        self.error_message = msg
        self.finished_at = datetime.now()
        self.save(update_fields=["state", "error_message", "finished_at"])

    def has_started(self):
        return self.state in ["STARTED", "FINISHED"]

class JungleProximity(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="jungle_proximity")
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    game_sequence_number = models.SmallIntegerField()
    game_time = models.SmallIntegerField()

    jungle_player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="jungle_proximity")

    top_proximity = models.FloatField()
    mid_proximity = models.FloatField()
    bot_proximity = models.FloatField()
    support_proximity = models.FloatField()

    avg_top_proximity = models.FloatField(default=0)
    avg_mid_proximity = models.FloatField(default=0)
    avg_bot_proximity = models.FloatField(default=0)
    avg_support_proximity = models.FloatField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['team', 'match', 'game_sequence_number']),  # For team_analysis
            models.Index(fields=['match', 'game_sequence_number', 'team']),  # For match_frontend_demo
            models.Index(fields=['jungle_player', 'game_time']),  # For player_view jungle queries
            models.Index(fields=['game_time']),  # For time-based aggregations
        ]

class ObjectiveEvents(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="objectives_match")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="objectives_team")
    objective_name = models.CharField(max_length=128, null=True, blank=True)
    objective_type = models.CharField(max_length=128, null=True, blank=True)
    objective_sequence_number = models.SmallIntegerField()
    game_time = models.SmallIntegerField()
    alive_time = models.SmallIntegerField()
    value = models.FloatField()

    gold_difference = models.IntegerField()
    gold_difference_30_seconds_after = models.SmallIntegerField(null=True)
    gold_difference_60_seconds_after = models.SmallIntegerField(null=True)
    gold_difference_30_seconds_before = models.SmallIntegerField(null=True)
    gold_difference_60_seconds_before = models.SmallIntegerField(null=True)
    xp_difference = models.IntegerField()
    xp_difference_30_seconds_after = models.SmallIntegerField(null=True)
    xp_difference_60_seconds_after = models.SmallIntegerField(null=True)
    xp_difference_30_seconds_before = models.SmallIntegerField(null=True)
    xp_difference_60_seconds_before = models.SmallIntegerField(null=True)
    kills_difference = models.SmallIntegerField(default=0)
    deaths_difference = models.SmallIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['team']),  # For teams_view team_ids query
            models.Index(fields=['team', 'objective_name']),  # For team_analysis objective stats
            models.Index(fields=['match', 'objective_sequence_number', 'team']),  # For match filtering
        ]



class GoldDifference(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="gold_difference")
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    game_sequence_number = models.SmallIntegerField()
    game_time = models.SmallIntegerField()
    net_worth = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['team', 'match', 'game_sequence_number']),  # For team_analysis gold queries
            models.Index(fields=['match', 'game_sequence_number']),  # For match_frontend_demo
            models.Index(fields=['team', 'game_time']),  # For time-based aggregations
            models.Index(fields=['game_time']),  # For cross-team gold difference calculations
        ]
