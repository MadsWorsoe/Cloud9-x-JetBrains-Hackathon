from .models import Champion, DraftAction, DraftSession
from matches.models import Team, Game
from django.db.models import Q, Count
from rest_framework.views import APIView
from rest_framework.response import Response
from .services.serializer import ChampionSerializer, TeamSerializer
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
import torch
import torch.nn.functional as F
import numpy as np
import os
import json

from .ml.model import DraftPolicyNet
from .ml.encoder import encode_state, get_uuid_to_roles, JSON_ROLE_TO_INTERNAL, ROLES, compute_role_pressure
from .ml.phase import get_draft_phase

ROLES_LOWER = ["top", "jungle", "mid", "bot", "support"]
from .ml.constants import DRAFT_PHASES
from .ml.utils import find_role_assignment
from .ml.analyzer import DeltaAnalyzer

from .machine_learning.model_v2 import DraftTransformerModel
from .machine_learning.analyzer_v2 import DeltaAnalyzerV2 as DeltaAnalyzerV3
from django.conf import settings

class ChampionListView(APIView):
    """
    Returns all champions.
    Cached server-side because this data is effectively static.
    """

    @method_decorator(cache_page(60 * 60 * 24))  # 24 hours
    def get(self, request):
        champions = Champion.objects.all().order_by("name")
        serializer = ChampionSerializer(champions, many=True)
        return Response(serializer.data)

class TeamListView(APIView):
    """
    Returns unique teams that have data in DraftAction, sorted by action count.
    """
    def get(self, request):
        # 1. Get counts of draft actions per drafter_id
        drafter_counts = dict(
            DraftAction.objects.values('drafter_id')
            .annotate(count=Count('id'))
            .values_list('drafter_id', 'count')
        )
        
        # 2. Get teams that have at least one draft action
        drafter_ids = [d for d in drafter_counts.keys() if d]
        teams = list(Team.objects.filter(external_id__in=drafter_ids))
        
        # 3. Attach count
        for team in teams:
            team.draft_action_count = drafter_counts.get(team.external_id, 0)
            
        # 4. Apply sorting logic:
        # Group 1: > 1000 actions, sorted alphabetically
        group1 = sorted([t for t in teams if t.draft_action_count > 1000], key=lambda x: (x.name or "").lower())
        # Group 2: <= 1000 actions, sorted alphabetically
        group2 = sorted([t for t in teams if t.draft_action_count <= 1000], key=lambda x: (x.name or "").lower())
        
        sorted_teams = group1 + group2
        
        serializer = TeamSerializer(sorted_teams, many=True)
        return Response(serializer.data)

class DraftSimilarMatchesView(APIView):
    """
    Returns matches where the same 10 champions were picked.
    """
    def post(self, request):
        picks = request.data.get("picks", {})
        blue_team = request.data.get("blue_team")
        red_team = request.data.get("red_team")
        
        def extract_ids(items):
            res = []
            for item in items:
                if not item: continue
                if isinstance(item, dict) and "id" in item: res.append(item["id"])
                else: res.append(str(item))
            return res

        blue_picks = extract_ids(picks.get("blue", []))
        red_picks = extract_ids(picks.get("red", []))
        
        all_picks = blue_picks + red_picks
        if len(all_picks) < 10:
            return Response({"matches": []})

        # 1. Games where 7 or more in all picks are counted (standard similarity)
        match_counts = dict(DraftAction.objects.filter(
            action_type='pick',
            champion_id__in=all_picks
        ).values('game').annotate(
            count=Count('champion', distinct=True)
        ).filter(count__gte=7).values_list('game', 'count'))

        game_ids = set(match_counts.keys())

        # 2. Games with team-specific composition matches
        blue_team_obj = Team.objects.filter(Q(external_id=blue_team) | Q(name=blue_team)).first()
        red_team_obj = Team.objects.filter(Q(external_id=red_team) | Q(name=red_team)).first()
        
        team_history_game_ids = set()

        # Helper to find games where a team played (either side) and had 4+ matches with a set of picks
        def get_team_composition_matches(team_obj, pick_ids):
            if not team_obj or not pick_ids:
                return set()
            
            # Find all games where this team played
            games_played = Game.objects.filter(
                Q(team_1=team_obj) | Q(team_2=team_obj)
            ).values_list('id', flat=True)
            
            # For those games, count how many of the pick_ids were picked by THIS team
            # We need to know which side the team was on in each game
            # This is slightly complex in a single query, so we can do it via DraftAction filtering by team
            matches = DraftAction.objects.filter(
                game_id__in=games_played,
                action_type='pick',
                drafter_id=team_obj.external_id,
                champion_id__in=pick_ids
            ).values('game').annotate(count=Count('id')).filter(count__gte=4).values_list('game', flat=True)
            
            return set(matches)

        if blue_team_obj and blue_picks:
            blue_team_matches = get_team_composition_matches(blue_team_obj, blue_picks)
            team_history_game_ids.update(blue_team_matches)

        if red_team_obj and red_picks:
            red_team_matches = get_team_composition_matches(red_team_obj, red_picks)
            team_history_game_ids.update(red_team_matches)

        game_ids.update(team_history_game_ids)

        # Make sure match_counts has entries for games in team_history_game_ids
        # so the match_count is correctly shown in the UI even if < 7
        missing_game_ids = team_history_game_ids - set(match_counts.keys())
        if missing_game_ids:
            missing_counts = DraftAction.objects.filter(
                action_type='pick',
                game_id__in=missing_game_ids,
                champion_id__in=all_picks
            ).values('game').annotate(
                count=Count('champion', distinct=True)
            ).values_list('game', 'count')
            match_counts.update(dict(missing_counts))

        from django.db.models import Prefetch
        games = Game.objects.filter(id__in=list(game_ids)).select_related('team_1', 'team_2', 'winning_team', 'match').prefetch_related(
            Prefetch('draft_actions', queryset=DraftAction.objects.filter(action_type='pick').select_related('champion'), to_attr='game_picks')
        )
        
        exact_matches = []
        similar_drafts = []
        team_history = []
        
        # Normalize draft team names/IDs for comparison
        draft_teams = set()
        if blue_team: draft_teams.add(blue_team.lower())
        if red_team: draft_teams.add(red_team.lower())

        # Keep a set of all_picks IDs for quick matching
        all_picks_set = set(all_picks)

        for g in games:
            count = match_counts.get(g.id, 0)
            is_highlighted = False
            g_teams = []
            if g.team_1:
                g_teams.append((g.team_1.name or "").lower())
                if g.team_1.external_id:
                    g_teams.append(g.team_1.external_id.lower())
            if g.team_2:
                g_teams.append((g.team_2.name or "").lower())
                if g.team_2.external_id:
                    g_teams.append(g.team_2.external_id.lower())
            
            if draft_teams and any(t in draft_teams for t in g_teams if t):
                is_highlighted = True

            g_blue_picks = [
                {"name": p.champion.name, "is_match": p.champion_id in all_picks_set} 
                for p in g.game_picks if p.team_side == 'blue'
            ]
            g_red_picks = [
                {"name": p.champion.name, "is_match": p.champion_id in all_picks_set} 
                for p in g.game_picks if p.team_side == 'red'
            ]

            match_data = {
                "game_id": g.game_id,
                "match_external_id": g.match.external_id if g.match else "Unknown",
                "tournament": g.match.tournament if g.match else "Unknown",
                "start_time": g.match.start_time.isoformat() if g.match and g.match.start_time else None,
                "team_1": (g.team_1.name or g.team_1.external_id) if g.team_1 else "Unknown",
                "team_1_logo": g.team_1.logo_url if g.team_1 else None,
                "team_2": (g.team_2.name or g.team_2.external_id) if g.team_2 else "Unknown",
                "team_2_logo": g.team_2.logo_url if g.team_2 else None,
                "winning_team": (g.winning_team.name or g.winning_team.external_id) if g.winning_team else "Unknown",
                "team_1_side": g.team_1_side,
                "blue_picks": g_blue_picks,
                "red_picks": g_red_picks,
                "is_highlighted": is_highlighted,
                "match_count": count
            }

            if count == 10:
                exact_matches.append(match_data)
            elif g.id in team_history_game_ids:
                team_history.append(match_data)
            else:
                similar_drafts.append(match_data)

        # Sort by match count descending, then by date descending
        similar_drafts.sort(key=lambda x: (x["match_count"], x["start_time"] or ""), reverse=True)
        exact_matches.sort(key=lambda x: (x["start_time"] or ""), reverse=True)
        team_history.sort(key=lambda x: (x["start_time"] or ""), reverse=True)

        return Response({
            "matches": exact_matches, # Keep for backward compatibility
            "exact_matches": exact_matches,
            "similar_drafts": similar_drafts,
            "team_history": team_history
        })

class DraftRecommendationView(APIView):
    """
    Provides champion recommendations based on the current draft state and selected teams.
    """
    _model_v2 = None
    _checkpoint_v2 = None
    _model_v3 = None
    _mappings_v3 = None

    @classmethod
    def load_model_v2(cls):
        if cls._model_v2 is None:
            model_path = os.path.join("draft", "ml_artifacts", "draft_model.pt")
            if not os.path.exists(model_path):
                return None
            
            cls._checkpoint_v2 = torch.load(model_path, map_location="cpu")
            cls._model_v2 = DraftPolicyNet(
                input_dim=cls._checkpoint_v2["input_dim"],
                num_champions=cls._checkpoint_v2["num_champions"],
                num_teams=cls._checkpoint_v2.get("num_teams", 100)
            )
            cls._model_v2.load_state_dict(cls._checkpoint_v2["model_state"])
            cls._model_v2.eval()
        return cls._model_v2

    @classmethod
    def load_model_v3(cls):
        if cls._model_v3 is None:
            model_path = os.path.join("draft", "ml_artifacts", "draft_model_v3.pth")
            mapping_path = os.path.join("draft", "ml_artifacts", "draft_mappings_v3.json")
            
            if not os.path.exists(model_path) or not os.path.exists(mapping_path):
                return None

            with open(mapping_path, 'r') as f:
                cls._mappings_v3 = json.load(f)
            
            cls._model_v3 = DraftTransformerModel(
                num_champions=cls._mappings_v3["num_champions"],
                num_teams=cls._mappings_v3["num_teams"]
            )
            cls._model_v3.load_state_dict(torch.load(model_path, map_location="cpu"))
            cls._model_v3.eval()
        return cls._model_v3

    def post(self, request):
        return self.get_recommendations(request)

    def get(self, request):
        return self.get_recommendations(request)

    def get_recommendations(self, request):
        # Determine version from query param or settings
        version = request.query_params.get("model") or request.data.get("model") or getattr(settings, 'DRAFT_MODEL_VERSION', 'v3')
        version = version.lower()

        if version == 'v3':
            return self.get_recommendations_v3(request)
        else:
            return self.get_recommendations_v2(request)

    def get_recommendations_v3(self, request):
        model = self.load_model_v3()
        if not model:
            return Response({"error": "V3 Model not found"}, status=500)

        mappings = self._mappings_v3
        champ_to_idx = mappings["champ_to_idx"]
        idx_to_name = mappings["idx_to_name"]
        num_champions = mappings["num_champions"]
        team_to_idx = mappings["team_to_idx"]

        data = request.data if request.method == "POST" else {}
        draft_id = data.get("draft_id") or request.query_params.get("draft_id")
        blue_team = data.get("blue_team")
        red_team = data.get("red_team")
        picks = data.get("picks", {})
        bans = data.get("bans", {})

        if not blue_team or not red_team or not picks or not bans:
            if draft_id:
                try:
                    draft = DraftSession.objects.get(id=draft_id)
                    blue_team = blue_team or draft.blue_team
                    red_team = red_team or draft.red_team
                    picks = picks or draft.picks
                    bans = bans or draft.bans
                except DraftSession.DoesNotExist:
                    return Response({"error": "Draft not found"}, status=404)
            else:
                return Response({"error": "Missing draft state"}, status=400)

        # Map teams to indices
        blue_team_obj = Team.objects.filter(Q(name=blue_team) | Q(external_id=blue_team)).first()
        red_team_obj = Team.objects.filter(Q(name=red_team) | Q(external_id=red_team)).first()

        blue_team_idx = team_to_idx.get(blue_team_obj.external_id if blue_team_obj else None, 0)
        red_team_idx = team_to_idx.get(red_team_obj.external_id if red_team_obj else None, 0)

        # Extract IDs
        def extract_ids(items):
            res = []
            for item in items:
                if not item: continue
                if isinstance(item, dict) and "id" in item: res.append(item["id"])
                else: res.append(str(item))
            return res

        blue_picks = extract_ids(picks.get("blue", []))
        red_picks = extract_ids(picks.get("red", []))
        blue_bans = extract_ids(bans.get("blue", []))
        red_bans = extract_ids(bans.get("red", []))

        total_actions = len(blue_picks) + len(red_picks) + len(blue_bans) + len(red_bans)
        if total_actions >= 20:
            return Response({"error": "Draft completed"}, status=400)

        side, action_type = DRAFT_PHASES[total_actions]
        curr_team_idx = blue_team_idx if side == 'blue' else red_team_idx
        opp_team_idx = red_team_idx if side == 'blue' else blue_team_idx

        # Prepare state for Transformer
        champ_ids = torch.full((1, 20), num_champions, dtype=torch.long)
        action_types = torch.zeros((1, 20), dtype=torch.long)
        sides_tensor = torch.zeros((1, 20), dtype=torch.long)
        positions = torch.arange(20).unsqueeze(0)

        # Reconstruct sequence properly
        # We use the DRAFT_PHASES to place champions in their correct temporal slot
        # This is crucial for the Transformer which cares about order.
        
        # Helper to get the n-th champion for a given (side, action)
        def get_champ_at_count(side_name, act_name, n):
            items = picks.get(side_name, []) if act_name == 'pick' else bans.get(side_name, [])
            if n < len(items) and items[n]:
                c_obj = items[n]
                return c_obj["id"] if isinstance(c_obj, dict) else str(c_obj)
            return None

        phase_counts = {"blue_pick": 0, "red_pick": 0, "blue_ban": 0, "red_ban": 0}
        
        for i in range(total_actions):
            s, a = DRAFT_PHASES[i]
            key = f"{s}_{a}"
            c_id = get_champ_at_count(s, a, phase_counts[key])
            phase_counts[key] += 1
            
            if c_id:
                champ_ids[0, i] = champ_to_idx.get(c_id, num_champions)
                action_types[0, i] = 1 if a == "ban" else 2
                sides_tensor[0, i] = 1 if s == "blue" else 2

        with torch.no_grad():
            logits = model(champ_ids, action_types, sides_tensor, positions, torch.tensor([curr_team_idx]), torch.tensor([opp_team_idx]))
            probs = torch.softmax(logits, dim=-1)[0]

        # Mask used champions
        mask = torch.ones_like(probs)
        for i in range(20):
            val = champ_ids[0, i].item()
            if val < num_champions:
                mask[val] = 0
        probs = probs * mask

        # Role viability penalty (V3 logic)
        analyzer = DeltaAnalyzerV3(
            model, champ_to_idx, mappings["idx_to_champ"], idx_to_name, 
            os.path.join("draft", "ml_artifacts", "champ_roles.json")
        )

        current_team_picks_uuids = blue_picks if side == 'blue' else red_picks
        opponent_team_picks_uuids = red_picks if side == 'blue' else blue_picks
        
        current_team_picks_names = list(Champion.objects.filter(id__in=current_team_picks_uuids).values_list('name', flat=True))
        opponent_team_picks_names = list(Champion.objects.filter(id__in=opponent_team_picks_uuids).values_list('name', flat=True))

        if action_type == "pick":
            for i in range(num_champions):
                if probs[i] > 0:
                    c_name = idx_to_name[str(i)]
                    if not analyzer.is_viable_pick(current_team_picks_names, c_name):
                        probs[i] *= 0.01

        elif action_type == "ban":
            for i in range(num_champions):
                if probs[i] > 0:
                    c_name = idx_to_name[str(i)]
                    # If the opponent cannot pick this champion anyway because they already filled its roles,
                    # then banning it is redundant.
                    if not analyzer.is_viable_pick(opponent_team_picks_names, c_name):
                        probs[i] *= 0.01

        # Final re-normalization and sorting
        probs_numpy = probs.numpy()
        total_p = np.sum(probs_numpy)
        if total_p > 0:
            probs_numpy /= total_p

        sorted_indices = np.argsort(probs_numpy)[::-1]
        
        # Prepare recommendations
        # Get names for hints/analysis
        all_bans_uuids = blue_bans + red_bans

        own_picks_names = current_team_picks_names
        enemy_picks_names = opponent_team_picks_names
        all_bans_names = list(Champion.objects.filter(id__in=all_bans_uuids).values_list('name', flat=True))

        baseline_name = idx_to_name[str(sorted_indices[1])] if len(sorted_indices) > 1 else None
        opp_side_val = 2 if side == 'blue' else 1

        recommendations = []
        for i, idx in enumerate(sorted_indices[:50]):
            if probs_numpy[idx] <= 0: break
            
            uuid = mappings["idx_to_champ"][str(idx)]
            name = idx_to_name[str(idx)]
            score = float(probs_numpy[idx])
            
            hints = {}
            if i < 10:
                # Role pressure hints
                curr_p_vec = analyzer.get_role_pressure(own_picks_names)
                new_p_vec = analyzer.get_role_pressure(own_picks_names + [name])
                
                pressure_diff = [curr_p_vec[r] - new_p_vec[r] for r in ROLES_LOWER]
                rel_roles = [ROLES_LOWER[j].upper() for j in range(len(ROLES_LOWER)) if pressure_diff[j] > 0.1]
                if rel_roles:
                    hints["pressure_reduction"] = rel_roles
                
                # Flexibility hints
                roles = analyzer.champ_roles.get(analyzer.normalize_name(name), [])
                if len(roles) > 1:
                    hints["flex_roles"] = roles
                
                # Strategic "Why" insight (Delta Analysis)
                hints["why"] = analyzer.analyze_pick(
                    name, own_picks_names, enemy_picks_names, all_bans_names, 
                    side, curr_team_idx, opp_team_idx, total_actions, baseline_name,
                    champ_ids, action_types, sides_tensor, positions, opp_side_val,
                    candidate_idx=int(idx),
                    is_ban=(action_type == "ban")
                )

            recommendations.append({
                "champion_id": uuid,
                "score": score,
                "hints": hints
            })

        return Response({
            "recommendations": recommendations,
            "side": side,
            "action_type": action_type,
            "role_pressure": [analyzer.get_role_pressure(own_picks_names)[r] for r in ROLES_LOWER],
            "insights": analyzer.get_general_insights(
                champ_ids, action_types, sides_tensor, positions, 
                curr_team_idx, opp_team_idx, 
                own_picks_names, enemy_picks_names, all_bans_names, 
                total_actions, side, action_type
            )
        })

    def get_recommendations_v2(self, request):
        model = self.load_model_v2()
        if not model:
            return Response({"error": "V2 Model not found"}, status=500)

        # Try to get data from request body first (POST), then from query params/DB (GET)
        data = request.data if request.method == "POST" else {}
        
        draft_id = data.get("draft_id") or request.query_params.get("draft_id")
        
        blue_team = data.get("blue_team")
        red_team = data.get("red_team")
        picks = data.get("picks", {})
        bans = data.get("bans", {})

        if not blue_team or not red_team or not picks or not bans:
            if not draft_id:
                return Response({"error": "draft_id or full state (blue_team, red_team, picks, bans) is required"}, status=400)
            
            try:
                draft = DraftSession.objects.get(id=draft_id)
                blue_team = blue_team or draft.blue_team
                red_team = red_team or draft.red_team
                picks = picks or draft.picks
                bans = bans or draft.bans
            except DraftSession.DoesNotExist:
                return Response({"error": "Draft not found"}, status=404)

        # Extract current state
        def extract_ids(items):
            ids = []
            for item in items:
                if not item: continue
                if isinstance(item, dict) and "id" in item:
                    ids.append(item["id"])
                else:
                    ids.append(str(item))
            return ids

        blue_picks = extract_ids(picks.get("blue", []))
        red_picks = extract_ids(picks.get("red", []))
        blue_bans = extract_ids(bans.get("blue", []))
        red_bans = extract_ids(bans.get("red", []))

        total_actions = len(blue_picks) + len(red_picks) + len(blue_bans) + len(red_bans)
        if total_actions >= len(DRAFT_PHASES):
            return Response({"error": "Draft is already completed"}, status=400)

        side, action_type = DRAFT_PHASES[total_actions]
        phase = get_draft_phase(total_actions)

        # Map teams to indices
        team_id_to_index = self._checkpoint_v2.get("team_id_to_index", {})
        
        blue_team_obj = None
        if blue_team:
            blue_team_obj = Team.objects.filter(Q(name=blue_team) | Q(external_id=blue_team)).first()
        
        red_team_obj = None
        if red_team:
            red_team_obj = Team.objects.filter(Q(name=red_team) | Q(external_id=red_team)).first()

        blue_team_idx = team_id_to_index.get(blue_team_obj.external_id if blue_team_obj else None, 0)
        red_team_idx = team_id_to_index.get(red_team_obj.external_id if red_team_obj else None, 0)

        if side.lower() == "blue":
            team_idx = blue_team_idx
            opp_team_idx = red_team_idx
        else:
            team_idx = red_team_idx
            opp_team_idx = blue_team_idx

        champion_id_to_index = self._checkpoint_v2["champion_id_to_index"]
        index_to_champion_id = {v: k for k, v in champion_id_to_index.items()}

        own_picks = blue_picks if side.lower() == "blue" else red_picks
        enemy_picks = red_picks if side.lower() == "blue" else blue_picks
        all_bans = blue_bans + red_bans

        # Encode state
        state_data = encode_state(
            own_picks=own_picks,
            enemy_picks=enemy_picks,
            banned_champions=all_bans,
            side=side,
            phase=phase,
            team_idx=team_idx,
            champion_id_to_index=champion_id_to_index
        )

        x_vec = np.concatenate([
            state_data["own_picks"],
            state_data["enemy_picks"],
            state_data["bans"],
            state_data["side"],
            state_data["phase"],
            state_data["role_pressure"]
        ])
        x_tensor = torch.tensor(x_vec, dtype=torch.float32).unsqueeze(0)
        t_tensor = torch.tensor([team_idx], dtype=torch.long)
        o_tensor = torch.tensor([opp_team_idx], dtype=torch.long)

        with torch.no_grad():
            logits = model(x_tensor, t_tensor, o_tensor)
            
            # Apply temperature to sharpen recommendations (T < 1.0 makes them more "opinionated")
            temperature = 0.5 
            probs = F.softmax(logits / temperature, dim=1).squeeze(0).numpy()

        # Mask illegal moves
        picked_banned_indices = []
        for uuid in blue_picks + red_picks + blue_bans + red_bans:
            if uuid in champion_id_to_index:
                picked_banned_indices.append(champion_id_to_index[uuid])
        
        probs_masked = probs.copy()
        for idx in picked_banned_indices:
            probs_masked[idx] = 0.0
        
        # Apply role penalty if it's a pick
        if action_type.lower() == "pick":
            mapping = get_uuid_to_roles()
            current_team_champ_roles = []
            for uuid in own_picks:
                roles = mapping.get(uuid, [])
                internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in roles]
                current_team_champ_roles.append([r for r in internal_roles if r])

            for i in range(len(probs_masked)):
                if probs_masked[i] == 0:
                    continue
                
                champ_uuid = index_to_champion_id[i]
                champ_roles = mapping.get(champ_uuid, [])
                if not champ_roles:
                    continue
                
                internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in champ_roles]
                internal_roles = [r for r in internal_roles if r]
                if not internal_roles:
                    continue
                
                test_roles = current_team_champ_roles + [internal_roles]
                if not find_role_assignment(test_roles):
                    probs_masked[i] *= 0.01
        
        # Apply redundant ban penalty
        elif action_type.lower() == "ban":
            mapping = get_uuid_to_roles()
            enemy_team_champ_roles = []
            for uuid in enemy_picks:
                roles = mapping.get(uuid, [])
                internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in roles]
                valid_roles = [r for r in internal_roles if r]
                if valid_roles:
                    enemy_team_champ_roles.append(valid_roles)

            for i in range(len(probs_masked)):
                if probs_masked[i] == 0:
                    continue
                
                champ_uuid = index_to_champion_id[i]
                champ_roles = mapping.get(champ_uuid, [])
                
                if not champ_roles:
                    continue
                
                internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in champ_roles]
                internal_roles = [r for r in internal_roles if r]
                if not internal_roles:
                    continue
                
                # If the enemy couldn't pick this champion anyway because they already filled its roles, 
                # banning it is redundant and should be penalized.
                test_roles = enemy_team_champ_roles + [internal_roles]
                if not find_role_assignment(test_roles):
                    probs_masked[i] *= 0.01

        # Re-normalize to make scores more meaningful (sum to 1.0 for valid options)
        total_prob = np.sum(probs_masked)
        if total_prob > 0:
            probs_masked /= total_prob

        # Sort recommendations
        sorted_indices = np.argsort(probs_masked)[::-1]

        # Delta Analyzer setup
        analyzer = DeltaAnalyzer(model, champion_id_to_index, index_to_champion_id)
        baseline_uuid = None
        if len(sorted_indices) > 1:
            baseline_uuid = index_to_champion_id[int(sorted_indices[1])]

        recommendations = []
        
        # We only do heavy hints for the top N recommendations to keep it fast
        HINT_LIMIT = 10 

        for i, idx in enumerate(sorted_indices[:50]): # Top 50
            if probs_masked[idx] <= 0:
                break
            
            uuid = index_to_champion_id[int(idx)]
            score = float(probs_masked[idx])
            
            hints = {}
            if i < HINT_LIMIT:
                # 1. Role pressure reduction (derived from current state)
                mapping = get_uuid_to_roles()
                champ_roles = mapping.get(uuid, [])
                internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in champ_roles]
                internal_roles = [r for r in internal_roles if r]
                
                curr_pressure = state_data["role_pressure"]
                temp_own_picks = own_picks + [uuid]
                new_pressure = compute_role_pressure(temp_own_picks, enemy_picks, all_bans)
                
                pressure_diff = curr_pressure - new_pressure
                rel_roles = [ROLES[j] for j in range(len(ROLES)) if pressure_diff[j] > 0.05]
                if rel_roles:
                    hints["pressure_reduction"] = rel_roles
                
                # 2. Flexibility
                if len(internal_roles) > 1:
                    hints["flex_roles"] = internal_roles
                
                # 3. Delta Analyzer (Lookahead "Why")
                if baseline_uuid and uuid != baseline_uuid:
                    hints["why"] = analyzer.analyze_pick(
                        uuid, own_picks, enemy_picks, all_bans, 
                        side, team_idx, opp_team_idx, total_actions, baseline_uuid,
                        is_ban=(action_type.lower() == "ban")
                    )

            recommendations.append({
                "champion_id": uuid,
                "score": score,
                "hints": hints
            })

        return Response({
            "recommendations": recommendations,
            "side": side,
            "action_type": action_type,
            "role_pressure": state_data["role_pressure"].tolist(),
        })