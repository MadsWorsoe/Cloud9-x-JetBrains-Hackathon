from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from draft.models import DraftAction, TeamChampionPickStats, TeamChampionBanStats, Champion
from matches.models import Team, Game

BLUE_SIDE = 'blue'
RED_SIDE = 'red'


class Command(BaseCommand):
    help = "Aggregate pick and ban statistics from DraftAction with bulk insert and low memory usage"

    def handle(self, *args, **options):
        self.stdout.write("Starting draft stats aggregation...")

        # Clear existing stats
        TeamChampionPickStats.objects.all().delete()
        TeamChampionBanStats.objects.all().delete()

        # Cache teams by external_id for fast lookup
        teams_cache = {t.external_id: t for t in Team.objects.all()}
        # Also cache teams by ID for lookup when we have team_1_id/team_2_id
        teams_by_id = {t.id: t for t in teams_cache.values()}

        pick_accumulator = {}
        ban_accumulator = {}

        actions_queryset = DraftAction.objects.select_related("game", "champion").iterator()
        total_actions = DraftAction.objects.count()

        self.stdout.write(f"Processing {total_actions} draft actions...")

        for action in tqdm(actions_queryset, total=total_actions, desc="Aggregating stats"):
            game = action.game
            champion = action.champion

            if not game or not champion:
                continue

            team = teams_cache.get(action.drafter_id)
            if not team:
                continue

            is_win = game.winning_team_id == team.id

            if game.team_1_id == team.id:
                side = game.team_1_side
                opponent_team = teams_by_id.get(game.team_2_id)
            elif game.team_2_id == team.id:
                side = game.team_2_side
                opponent_team = teams_by_id.get(game.team_1_id)
            else:
                continue

            if action.action_type == "pick":
                key = (team.id, champion.id)
                if key not in pick_accumulator:
                    pick_accumulator[key] = {
                        'team': team,
                        'champion': champion,
                        'wins': 0,
                        'games_played': 0,
                        'red_side_wins': 0,
                        'red_side_games': 0,
                        'blue_side_wins': 0,
                        'blue_side_games': 0,
                    }

                stats = pick_accumulator[key]
                stats['games_played'] += 1
                if is_win:
                    stats['wins'] += 1

                if side == BLUE_SIDE:
                    stats['blue_side_games'] += 1
                    if is_win:
                        stats['blue_side_wins'] += 1
                elif side == RED_SIDE:
                    stats['red_side_games'] += 1
                    if is_win:
                        stats['red_side_wins'] += 1

            elif action.action_type == "ban":
                # Self stats
                self_key = (team.id, champion.id)
                if self_key not in ban_accumulator:
                    ban_accumulator[self_key] = self._init_ban_stats(team, champion)

                s_stats = ban_accumulator[self_key]
                s_stats['games_banned'] += 1
                s_stats['total_self_bans'] += 1
                if is_win:
                    s_stats['wins'] += 1

                if side == BLUE_SIDE:
                    s_stats['blue_side_self_bans'] += 1
                    if is_win:
                        s_stats['blue_side_self_wins'] += 1
                elif side == RED_SIDE:
                    s_stats['red_side_self_bans'] += 1
                    if is_win:
                        s_stats['red_side_self_wins'] += 1

                # Opponent stats
                if opponent_team:
                    opp_key = (opponent_team.id, champion.id)
                    if opp_key not in ban_accumulator:
                        ban_accumulator[opp_key] = self._init_ban_stats(opponent_team, champion)

                    o_stats = ban_accumulator[opp_key]
                    o_stats['games_banned'] += 1
                    o_stats['total_opponent_bans'] += 1

                    opponent_won = not is_win
                    if opponent_won:
                        o_stats['wins'] += 1

                    opponent_side = RED_SIDE if side == BLUE_SIDE else BLUE_SIDE
                    if opponent_side == BLUE_SIDE:
                        o_stats['blue_side_opponent_bans'] += 1
                        if opponent_won:
                            o_stats['blue_side_opponent_wins'] += 1
                    elif opponent_side == RED_SIDE:
                        o_stats['red_side_opponent_bans'] += 1
                        if opponent_won:
                            o_stats['red_side_opponent_wins'] += 1

        # Bulk insert
        self.stdout.write("Inserting new stats...")

        pick_objects = [TeamChampionPickStats(**stats) for stats in pick_accumulator.values()]
        ban_objects = [TeamChampionBanStats(**stats) for stats in ban_accumulator.values()]

        with transaction.atomic():
            TeamChampionPickStats.objects.bulk_create(pick_objects, batch_size=1000)
            TeamChampionBanStats.objects.bulk_create(ban_objects, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Draft stats aggregation complete. Created {len(pick_objects)} pick records and {len(ban_objects)} ban records."))

    def _init_ban_stats(self, team, champion):
        return {
            'team': team,
            'champion': champion,
            'games_banned': 0,
            'wins': 0,
            'total_self_bans': 0,
            'blue_side_self_bans': 0,
            'blue_side_self_wins': 0,
            'red_side_self_bans': 0,
            'red_side_self_wins': 0,
            'total_opponent_bans': 0,
            'red_side_opponent_bans': 0,
            'red_side_opponent_wins': 0,
            'blue_side_opponent_bans': 0,
            'blue_side_opponent_wins': 0,
        }
