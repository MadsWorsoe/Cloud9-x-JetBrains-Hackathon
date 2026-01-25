from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from math import exp
from datetime import timedelta

from matches.models import Game
from draft.models import DraftAction, TeamChampionPickStats, TeamChampionBanStats


HALF_LIFE_DAYS = 60  # meta decay speed


def time_decay_weight(game_time, now):
    delta_days = (now - game_time).days
    return exp(-delta_days / HALF_LIFE_DAYS)


class Command(BaseCommand):
    help = "Build time-decayed analytical stats for picks and bans"

    def handle(self, *args, **kwargs):
        now = timezone.now()

        TeamChampionPickStats.objects.all().delete()
        TeamChampionBanStats.objects.all().delete()

        pick_accumulator = {}
        ban_accumulator = {}

        for game in Game.objects.select_related("winning_team"):
            if not game.match or not game.match.start_time:
                continue

            weight = time_decay_weight(game.match.start_time, now)

            actions = DraftAction.objects.filter(game=game)

            for action in actions:
                key = (action.drafter_id, action.champion_id, action.team_side)

                if action.action_type == "pick":
                    if key not in pick_accumulator:
                        pick_accumulator[key] = {"games": 0.0, "wins": 0.0}

                    pick_accumulator[key]["games"] += weight
                    if game.winning_team_id == action.drafter_id:
                        pick_accumulator[key]["wins"] += weight

                elif action.action_type == "ban":
                    key = (action.drafter_id, action.champion_id)
                    if key not in ban_accumulator:
                        ban_accumulator[key] = {"bans": 0.0}

                    ban_accumulator[key]["bans"] += weight

        with transaction.atomic():
            for (team_id, champ_id, side), stats in pick_accumulator.items():
                TeamChampionPickStats.objects.create(
                    team_id=team_id,
                    champion_id=champ_id,
                    side=side,
                    games_played=stats["games"],
                    wins=stats["wins"],
                    winrate=stats["wins"] / stats["games"] if stats["games"] > 0 else 0.0,
                )

            for (team_id, champ_id), stats in ban_accumulator.items():
                TeamChampionBanStats.objects.create(
                    team_id=team_id,
                    champion_id=champ_id,
                    bans_against=stats["bans"],
                )

        self.stdout.write(self.style.SUCCESS("Time-decayed stats built successfully"))
