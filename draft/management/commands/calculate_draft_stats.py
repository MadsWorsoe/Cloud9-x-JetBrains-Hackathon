from django.core.management.base import BaseCommand
from matches.models import Game
from draft.models import Champion
import json
from collections import defaultdict
import numpy as np

from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Calculate Champion Synergy and Counter Stats with Time Decay"

    def handle(self, *args, **options):
        self.stdout.write("Calculating synergies and counters (weighted by recency)...")
        
        now = timezone.now()
        half_life_days = 180.0 # 6 months
        
        games = Game.objects.filter(winning_team__isnull=False).select_related('match')
        
        # champ_id -> total_games, total_wins
        champ_stats = defaultdict(lambda: {"games": 0, "wins": 0})
        # (id1, id2) -> games, wins (same team)
        synergy_stats = defaultdict(lambda: {"games": 0, "wins": 0})
        # (id1, id2) -> games, wins (id1 vs id2, wins for id1)
        counter_stats = defaultdict(lambda: {"games": 0, "wins": 0})

        for game in games:
            # Calculate Weight
            game_time = game.match.start_time if game.match and game.match.start_time else (now - timedelta(days=365))
            days_diff = (now - game_time).days
            weight = 0.5 ** (days_diff / half_life_days)

            blue_champs = [
                game.team_1_top_champion, game.team_1_jungle_champion,
                game.team_1_mid_champion, game.team_1_bot_champion,
                game.team_1_support_champion
            ]
            red_champs = [
                game.team_2_top_champion, game.team_2_jungle_champion,
                game.team_2_mid_champion, game.team_2_bot_champion,
                game.team_2_support_champion
            ]
            
            # Clean None and empty
            blue_champs = [c for c in blue_champs if c]
            red_champs = [c for c in red_champs if c]
            
            blue_won = game.winning_team_id == (game.team_1_id if game.team_1_side == 'blue' else game.team_2_id)
            
            # Update individual stats
            for c in blue_champs:
                champ_stats[c]["games"] += weight
                if blue_won: champ_stats[c]["wins"] += weight
            for c in red_champs:
                champ_stats[c]["games"] += weight
                if not blue_won: champ_stats[c]["wins"] += weight
                
            # Update Synergies
            def update_synergy(champs, won, w):
                for i in range(len(champs)):
                    for j in range(i + 1, len(champs)):
                        pair = tuple(sorted([champs[i], champs[j]]))
                        synergy_stats[pair]["games"] += w
                        if won: synergy_stats[pair]["wins"] += w
            
            update_synergy(blue_champs, blue_won, weight)
            update_synergy(red_champs, not blue_won, weight)
            
            # Update Counters
            for bc in blue_champs:
                for rc in red_champs:
                    # blue vs red
                    pair = (bc, rc)
                    counter_stats[pair]["games"] += weight
                    if blue_won: counter_stats[pair]["wins"] += weight
                    
                    # red vs blue
                    pair2 = (rc, bc)
                    counter_stats[pair2]["games"] += weight
                    if not blue_won: counter_stats[pair2]["wins"] += weight

        # Process into final scores with smoothing
        final_synergy = {}
        for pair, stats in synergy_stats.items():
            if stats["games"] < 2: continue
            # P(W | A, B) / (P(W|A) * P(W|B))? No, simpler:
            # Winrate of pair - (avg winrate of A and B)
            wr_a = champ_stats[pair[0]]["wins"] / champ_stats[pair[0]]["games"]
            wr_b = champ_stats[pair[1]]["wins"] / champ_stats[pair[1]]["games"]
            wr_pair = stats["wins"] / stats["games"]
            final_synergy["|".join(pair)] = wr_pair - (wr_a + wr_b) / 2

        final_counter = {}
        for pair, stats in counter_stats.items():
            if stats["games"] < 2: continue
            wr_a = champ_stats[pair[0]]["wins"] / champ_stats[pair[0]]["games"]
            wr_pair = stats["wins"] / stats["games"]
            # If wr_pair > wr_a, then A is good against B
            final_counter["|".join(pair)] = wr_pair - wr_a

        output = {
            "synergy": final_synergy,
            "counter": final_counter,
            "champ_avg_wr": {c: s["wins"]/s["games"] for c, s in champ_stats.items() if s["games"] > 0}
        }
        
        import os
        os.makedirs("draft/ml_artifacts", exist_ok=True)
        with open("draft/ml_artifacts/synergy_counter.json", "w") as f:
            json.dump(output, f)
            
        self.stdout.write(self.style.SUCCESS("Saved synergy and counter stats."))
