from django.core.management.base import BaseCommand
from matches.models import Game
from draft.models import Champion
import json
from collections import defaultdict
from pathlib import Path

class Command(BaseCommand):
    help = "Calculate most frequent roles for each champion"

    def handle(self, *args, **options):
        self.stdout.write("Calculating champion roles...")
        
        # champ_name -> {role -> count}
        role_counts = defaultdict(lambda: defaultdict(int))
        
        games = Game.objects.all()
        
        roles = ['top', 'jungle', 'mid', 'bot', 'support']
        
        for game in games:
            for side in ['team_1', 'team_2']:
                for role in roles:
                    field = f"{side}_{role}_champion"
                    champ_name = getattr(game, field)
                    if champ_name:
                        role_counts[champ_name][role] += 1
        
        # Process into primary roles (e.g. any role with > 10% frequency)
        champ_roles = {}
        for champ_name, counts in role_counts.items():
            total = sum(counts.values())
            if total == 0: continue
            
            # Sort roles by frequency
            sorted_roles = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            
            # A champion can have multiple roles if they are played there significantly
            # For simulation, let's take roles with at least 15% of games
            primary_roles = [role for role, count in sorted_roles if (count / total) >= 0.15]
            
            # Ensure at least one role
            if not primary_roles and sorted_roles:
                primary_roles = [sorted_roles[0][0]]
                
            champ_roles[champ_name] = primary_roles
            
        # Save to artifact
        output_dir = Path("draft/ml_artifacts")
        output_dir.mkdir(exist_ok=True, parents=True)
        
        with open(output_dir / "champ_roles.json", "w") as f:
            json.dump(champ_roles, f, indent=4)
            
        self.stdout.write(self.style.SUCCESS(f"Saved roles for {len(champ_roles)} champions to champ_roles.json"))
