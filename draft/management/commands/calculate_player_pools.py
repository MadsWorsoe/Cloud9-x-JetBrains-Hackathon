from django.core.management.base import BaseCommand
from matches.models import Game
import json
from collections import defaultdict

from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Calculate Player Champion Pool Stats with Time Decay"

    def handle(self, *args, **options):
        self.stdout.write("Calculating player pools (weighted by recency)...")
        
        now = timezone.now()
        half_life_days = 180.0
        
        games = Game.objects.filter(winning_team__isnull=False).select_related('match')
        
        # (player_name, champ_name) -> games, wins
        player_champ_stats = defaultdict(lambda: {"games": 0, "wins": 0})

        for game in games:
            # Calculate Weight
            game_time = game.match.start_time if game.match and game.match.start_time else (now - timedelta(days=365))
            days_diff = (now - game_time).days
            weight = 0.5 ** (days_diff / half_life_days)

            players_champs = [
                (game.team_1_top_player_name, game.team_1_top_champion),
                (game.team_1_jungle_player_name, game.team_1_jungle_champion),
                (game.team_1_mid_player_name, game.team_1_mid_champion),
                (game.team_1_bot_player_name, game.team_1_bot_champion),
                (game.team_1_support_player_name, game.team_1_support_champion),
                (game.team_2_top_player_name, game.team_2_top_champion),
                (game.team_2_jungle_player_name, game.team_2_jungle_champion),
                (game.team_2_mid_player_name, game.team_2_mid_champion),
                (game.team_2_bot_player_name, game.team_2_bot_champion),
                (game.team_2_support_player_name, game.team_2_support_champion),
            ]
            
            blue_won = game.winning_team_id == (game.team_1_id if game.team_1_side == 'blue' else game.team_2_id)
            
            for i, (player, champ) in enumerate(players_champs):
                if not player or not champ: continue
                
                # First 5 are team 1, next 5 are team 2
                player_won = blue_won if (i < 5) == (game.team_1_side == 'blue') else not blue_won
                
                key = f"{player}|{champ}"
                player_champ_stats[key]["games"] += weight
                if player_won: player_champ_stats[key]["wins"] += weight

        # Smooth with average winrate?
        # For now just save raw
        import os
        os.makedirs("draft/ml_artifacts", exist_ok=True)
        with open("draft/ml_artifacts/player_pools.json", "w") as f:
            json.dump(player_champ_stats, f)
            
        self.stdout.write(self.style.SUCCESS("Saved player pool stats."))
