# drafts/views.py
from .models import DraftSession as Draft, TeamChampionPickStats, TeamChampionBanStats, DraftAction
from rest_framework.response import Response
from rest_framework.views import APIView
from matches.models import Team
from django.db.models import Q, Count

class DraftCreateView(APIView):
    def post(self, request):
        # Allow creating a draft with initial data (e.g. for copying/cloning)
        blue_team = request.data.get("blue_team")
        red_team = request.data.get("red_team")
        picks = request.data.get("picks", {
            "blue": [None] * 5,
            "red": [None] * 5,
        })
        bans = request.data.get("bans", {
            "blue": [None] * 5,
            "red": [None] * 5,
        })

        draft = Draft.objects.create(
            blue_team=blue_team,
            red_team=red_team,
            picks=picks,
            bans=bans,
            status="IN_PROGRESS" if any([blue_team, red_team]) else "CREATED"
        )
        return Response({
            "id": draft.id,
            "draft": serialize_draft(draft),
        })

class DraftDetailView(APIView):
    def get(self, request, draft_id):
        draft = Draft.objects.get(id=draft_id)
        return Response(serialize_draft(draft))

class DraftUpdateView(APIView):
    def patch(self, request, draft_id):
        draft = Draft.objects.get(id=draft_id)

        for field in ["blue_team", "red_team", "picks", "bans", "status"]:
            if field in request.data:
                setattr(draft, field, request.data[field])

        draft.save()
        return Response(serialize_draft(draft))

def serialize_draft(draft):
    stats = {"blue": {}, "red": {}}
    ban_stats_data = {"blue": {}, "red": {}}
    
    # Check if draft is finished. Short-circuit if not.
    blue_picks = draft.picks.get("blue", [])
    red_picks = draft.picks.get("red", [])
    total_picks = len([p for p in blue_picks if p]) + len([p for p in red_picks if p])
    
    is_finished = draft.status == "COMPLETED" or total_picks >= 10
    
    # Pre-fetch stats if teams are selected
    if draft.blue_team or draft.red_team:
        blue_team_obj = Team.objects.filter(Q(name=draft.blue_team) | Q(external_id=draft.blue_team)).first()
        red_team_obj = Team.objects.filter(Q(name=draft.red_team) | Q(external_id=draft.red_team)).first()
        
        # Calculate unique games per team for banrate percentages
        team_side_total_games = {}
        for team_obj in [blue_team_obj, red_team_obj]:
            if team_obj and team_obj.external_id:
                # Total games
                total = DraftAction.objects.filter(drafter_id=team_obj.external_id).values('game').distinct().count()
                # Blue side games
                blue_total = DraftAction.objects.filter(drafter_id=team_obj.external_id, team_side='blue').values('game').distinct().count()
                # Red side games
                red_total = DraftAction.objects.filter(drafter_id=team_obj.external_id, team_side='red').values('game').distinct().count()
                
                team_side_total_games[team_obj.external_id] = {
                    "total": total,
                    "blue": blue_total,
                    "red": red_total
                }

        def get_team_stats(team_obj, side):
            if not team_obj:
                return
            
            # Get IDs of picked champions for this side
            side_picks = draft.picks.get(side, [])
            champ_ids = [p["id"] if isinstance(p, dict) else p for p in side_picks if p]
            
            if champ_ids:
                pick_stats = TeamChampionPickStats.objects.filter(
                    team=team_obj,
                    champion_id__in=champ_ids
                )
                
                # Create a map for easy lookup
                pick_stats_map = {str(s.champion_id): s for s in pick_stats}
                
                for cid in champ_ids:
                    s = pick_stats_map.get(str(cid))
                    team_games = team_side_total_games.get(team_obj.external_id, {"total": 0, "blue": 0, "red": 0})
                    if s:
                        stats[side][str(cid)] = {
                            "wins": s.wins,
                            "games_played": s.games_played,
                            "winrate": round(s.wins / s.games_played * 100, 1) if s.games_played > 0 else 0,
                            "pickrate": round(s.games_played / team_games["total"] * 100, 1) if team_games["total"] > 0 else 0,
                            
                            "blue_side_wins": s.blue_side_wins,
                            "blue_side_games": s.blue_side_games,
                            "blue_side_winrate": round(s.blue_side_wins / s.blue_side_games * 100, 1) if s.blue_side_games > 0 else 0,
                            "blue_side_pickrate": round(s.blue_side_games / team_games["blue"] * 100, 1) if team_games["blue"] > 0 else 0,
                            
                            "red_side_wins": s.red_side_wins,
                            "red_side_games": s.red_side_games,
                            "red_side_winrate": round(s.red_side_wins / s.red_side_games * 100, 1) if s.red_side_games > 0 else 0,
                            "red_side_pickrate": round(s.red_side_games / team_games["red"] * 100, 1) if team_games["red"] > 0 else 0,
                        }
                    else:
                        stats[side][str(cid)] = {
                            "wins": 0, "games_played": 0, "winrate": 0, "pickrate": 0,
                            "blue_side_wins": 0, "blue_side_games": 0, "blue_side_winrate": 0, "blue_side_pickrate": 0,
                            "red_side_wins": 0, "red_side_games": 0, "red_side_winrate": 0, "red_side_pickrate": 0,
                        }

            # Get IDs of banned champions for this side
            side_bans = draft.bans.get(side, [])
            ban_champ_ids = [p["id"] if isinstance(p, dict) else p for p in side_bans if p]

            if ban_champ_ids:
                opp_side = "red" if side == "blue" else "blue"
                opp_team_obj = red_team_obj if side == "blue" else blue_team_obj
                
                if opp_team_obj:
                    ban_stats = TeamChampionBanStats.objects.filter(
                        team=opp_team_obj,
                        champion_id__in=ban_champ_ids
                    )
                    ban_stats_map = {str(s.champion_id): s for s in ban_stats}

                    for cid in ban_champ_ids:
                        s = ban_stats_map.get(str(cid))
                        opp_games = team_side_total_games.get(opp_team_obj.external_id, {"total": 0, "blue": 0, "red": 0})
                        
                        if s:
                            ban_stats_data[side][str(cid)] = {
                                "total_opponent_bans": s.total_opponent_bans,
                                "blue_side_opponent_bans": s.blue_side_opponent_bans,
                                "red_side_opponent_bans": s.red_side_opponent_bans,
                                "total_self_bans": s.total_self_bans,
                                "blue_side_self_bans": s.blue_side_self_bans,
                                "red_side_self_bans": s.red_side_self_bans,
                                
                                # Percentages
                                "opponent_banrate": round(s.total_opponent_bans / opp_games["total"] * 100, 1) if opp_games["total"] > 0 else 0,
                                "blue_side_opponent_banrate": round(s.blue_side_opponent_bans / opp_games["blue"] * 100, 1) if opp_games["blue"] > 0 else 0,
                                "red_side_opponent_banrate": round(s.red_side_opponent_bans / opp_games["red"] * 100, 1) if opp_games["red"] > 0 else 0,
                                
                                "self_banrate": round(s.total_self_bans / opp_games["total"] * 100, 1) if opp_games["total"] > 0 else 0,
                                "blue_side_self_banrate": round(s.blue_side_self_bans / opp_games["blue"] * 100, 1) if opp_games["blue"] > 0 else 0,
                                "red_side_self_banrate": round(s.red_side_self_bans / opp_games["red"] * 100, 1) if opp_games["red"] > 0 else 0,
                                
                                "opp_total_games": opp_games["total"],
                                "opp_blue_games": opp_games["blue"],
                                "opp_red_games": opp_games["red"],
                            }
                        else:
                            ban_stats_data[side][str(cid)] = {
                                "total_opponent_bans": 0, "blue_side_opponent_bans": 0, "red_side_opponent_bans": 0,
                                "total_self_bans": 0, "blue_side_self_bans": 0, "red_side_self_bans": 0,
                                "opponent_banrate": 0, "blue_side_opponent_banrate": 0, "red_side_opponent_banrate": 0,
                                "self_banrate": 0, "blue_side_self_banrate": 0, "red_side_self_banrate": 0,
                                "opp_total_games": opp_games["total"], "opp_blue_games": opp_games["blue"], "opp_red_games": opp_games["red"],
                            }

        get_team_stats(blue_team_obj, "blue")
        get_team_stats(red_team_obj, "red")

    return {
        "id": str(draft.id),
        "blue_team": draft.blue_team,
        "red_team": draft.red_team,
        "picks": draft.picks,
        "bans": draft.bans,
        "status": draft.status,
        "updated_at": draft.updated_at,
        "stats": stats,
        "ban_stats": ban_stats_data,
    }
