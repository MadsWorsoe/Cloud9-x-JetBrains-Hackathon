import numpy as np
from draft.models import (
    TeamChampionPickStats,
    TeamChampionBanStats,
)
from matches.models import Game


def safe_rate(wins, games):
    return wins / games if games > 0 else 0.0


def build_training_rows():
    """
    Returns:
        X: np.ndarray
        y: np.ndarray
    """

    X = []
    y = []

    pick_stats = (
        TeamChampionPickStats.objects
        .select_related("team", "champion")
    )

    for ps in pick_stats:
        team = ps.team
        champion = ps.champion

        # Find games where this champion was picked by this team
        games = Game.objects.filter(
            draft_actions__champion=champion,
            draft_actions__action_type="pick",
            draft_actions__team_side__iexact=models.F("winner_side"),
        ).distinct()

        if not games.exists():
            continue

        ban_stats = TeamChampionBanStats.objects.filter(
            team=team,
            champion=champion
        ).first()

        # Team features
        team_pick_winrate = safe_rate(ps.wins, ps.games_played)
        team_pick_rate = ps.games_played

        team_blue_wr = safe_rate(ps.blue_side_wins, ps.blue_side_games)
        team_red_wr = safe_rate(ps.red_side_wins, ps.red_side_games)

        team_self_ban_rate = (
            ban_stats.total_self_bans if ban_stats else 0
        )
        team_self_ban_wr = safe_rate(
            ban_stats.wins, ban_stats.games_banned
        ) if ban_stats else 0

        for game in games:
            opponent = (
                game.team_red if team == game.team_blue
                else game.team_blue
            )

            opp_pick = TeamChampionPickStats.objects.filter(
                team=opponent,
                champion=champion
            ).first()

            opp_ban = TeamChampionBanStats.objects.filter(
                team=opponent,
                champion=champion
            ).first()

            opp_pick_wr = safe_rate(
                opp_pick.wins, opp_pick.games_played
            ) if opp_pick else 0

            opp_pick_rate = opp_pick.games_played if opp_pick else 0
            opp_self_ban_rate = opp_ban.total_self_bans if opp_ban else 0

            is_blue = int(game.team_blue == team)
            win = int(game.winner == team)

            X.append([
                team_pick_winrate,
                team_pick_rate,
                team_blue_wr,
                team_red_wr,
                team_self_ban_rate,
                team_self_ban_wr,
                opp_pick_wr,
                opp_pick_rate,
                opp_self_ban_rate,
                is_blue,
            ])

            y.append(win)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)
