import json
import time
import pandas
import numpy as np

import traceback

from django.core.management.base import BaseCommand
from django.db.models import Sum

import matches.analysis as match_analysis
from draft.models import Champion, DraftAction
from matches.models import *
from matches.graphql.utils import graphql_utils, graphql_queries
from matches.utils import league_utils
from matches.utils.league_utils import MID_ROLE

DEBUG = False
WARD_ITEM_IDS = {
    # Stealth Ward
    "93d4e779-86fe-3e64-bf65-5c19fe10119c" : "stealth_ward",
    #Control Ward
    "7b101664-c419-37d5-94a8-7f6143c2bce6" : "control_ward",
    #Runic Compass
    "ee2268e2-eb71-39bf-9d20-68a4a1b08f22" : "stealth_ward",
    #Celestial Opposition
    "5d786793-d0bd-35a1-a5f6-d70b4d58ce3c" : "stealth_ward",
    #Dream Maker
    "00de0c4a-271f-36c2-9fb6-0d1dce3b0fe3" : "stealth_ward",

}

def clear_table_data(match_id, model):
    match = Match.objects.get(pk=match_id)
    deleted_count, _ = model.objects.filter(match=match).delete()
    print(f"Deleted {deleted_count} existing {model} for match {match_id}")


def generate_player_frames(match: Match, match_metadata, self=None):
    frames = Frame.objects.filter(match=match).order_by("updated_at")
    self.stdout.write(f"Processing {frames.count()} frames for match {match.external_id}")
    players_with_items = match_metadata["players"]
    player_name_to_id = {name: id_ for id_, name in players_with_items.items()}

    for frame in frames:
        try:
            if DEBUG:
                print(frame.raw_payload)
            # frame_data = json.loads(frame.raw_payload)
            frame_data = frame.raw_payload['seriesState']["games"][-1]
            if DEBUG:
                print(frame.raw_payload['seriesState']["games"][-1]['clock']['currentSeconds'])
        except json.JSONDecodeError:
            self.stderr.write(f"Skipping invalid JSON frame {frame.match.id}")
            continue

        game_time = frame.raw_payload['seriesState']["games"][-1]['clock']['currentSeconds']
        game_id = len(frame.raw_payload['seriesState']['games'])

        if game_time % 30 == 0:
            self.stderr.write(f"Match # {match.id}: Analyzing game time {game_time} on game #{game_id}")

        if DEBUG:
            time.sleep(10)

        if not game_time:
            self.stderr.write(f"invalid game_time")
            continue

        obj = []

        for team in frame_data['teams']:
            # print(team['name'])
            for player in team['players']:
                # print(player_json['name'])
                #player = Player.objects.get(external_id=player_json['id'])

                if "id" not in player:
                    player["id"] = player_name_to_id[player["name"]]

                if "position" not in player:
                    # print(f"The following player has no position??? {player}")
                    continue

                # TODO: Remove, we don't do Wards here anymore
                #print(player_json)
                # trinket = None
                # num_control_wards = 0
                # inventory = player.get("inventory", [])
                # if inventory:
                #     for item in inventory["items"]:
                #         if "Farsight Alteration" == item["name"]:
                #             trinket = "Farsight Alteration"
                #         if "Oracle Lens" == item["name"]:
                #             trinket = "Oracle Lens"
                #         if "Stealth Ward" == item["name"]:
                #             trinket = "Stealth Ward"
                #         if "Control Ward" == item["name"]:
                #             num_control_wards = item["equipped"]

                obj.append(PlayerFrames(
                    match=match,
                    player_id=Player.objects.filter(external_id=player["id"]).values("id"),
                    game_time=game_time,
                    game_id=game_id,
                    position_x=int(player["position"]["x"]),
                    position_y=int(player["position"]["y"]),
                    vision_score=player.get("visionScore", -1),
                    kills=player.get("kills", -1),
                    deaths=player.get("deaths", -1),
                    gold=player.get("netWorth", -1),
                    experience=player.get("experiencePoints", -1),
                    is_alive=player.get("alive", True),
                    # inventory=inventory,
                    # trinket=trinket,
                    # num_control_wards=num_control_wards
                ))

        PlayerFrames.objects.bulk_create(obj)


def get_metadata_for_match(match: Match):
    final_series_state = graphql_utils.make_request(
        graphql_utils.GRAPHQL_LIVE_DATA_FEED_SERIES_STATE_API_URL,
        graphql_queries.SERIES_FINISHED,
        {"series_id": match.external_id},
    )

    if final_series_state is None:
        last_frame = Frame.objects.filter(match=match).values("raw_payload").last()
        final_series_state = last_frame["raw_payload"]

    print(final_series_state)

    teams = final_series_state["seriesState"]["teams"]
    # print(teams)
    winning_team = None
    players = {}
    team_external_ids = {}

    for team in teams:
        team_id = Team.objects.filter(external_id=team["id"]).values("id")

        team_external_ids.update({team["id"] : team_id})

        if team["won"]:
            winning_team = team["id"]

        for player in team["players"]:
            players.update({player["id"]: player["name"]})


    return {
        "last_live_series_state": final_series_state["seriesState"],
        "players": players,
        "teams": teams,
        "winning_team": winning_team,
        "team_external_ids" : team_external_ids,
        "games" : final_series_state["seriesState"]["games"],
    }


def save_match_scores(match: Match, match_scores):
    if DEBUG:
        print(match_scores["teams"])
        print(match.team_1.external_id)
    team_1_score = next((team["score"] for team in match_scores["teams"] if team["id"] == match.team_1.external_id), None)
    team_2_score = next((team["score"] for team in match_scores["teams"] if team["id"] == match.team_2.external_id), None)
    #team_2_score = next((team["score"] for team in match_scores["teams"] if team["id"] == match.team_2), None)

    if DEBUG:
        print("team_1_score", team_1_score)
        print("team_2_score", team_2_score)
        #print(match_scores)
        print("winner", match_scores["winning_team"])

    match.winning_team = Team.objects.get(external_id=match_scores["winning_team"])
    match.team_1_score = team_1_score
    match.team_2_score = team_2_score

    if DEBUG:
        print("match", match)
    match.save()

    winning_team = 0

    # Add values to Game Table
    for game in match_scores["games"]:

        game_obj = []

        for team in game["teams"]:

            team_obj = {"id": team["id"], "side": team["side"]}

            if team["won"]:
                winning_team = team["id"]
                team_obj["score"] = 1
            else:
                team_obj["score"] = 0

            for player in team["players"]:
                player_role = Player.objects.filter(external_id=player["id"]).values("role")[0]

                if "character" not in player:
                    print("Player", player["id"], "has no character")
                    print(team["players"])
                    continue

                team_obj[player_role["role"] + "_player"] = player["id"]
                team_obj[player_role["role"] + "_champion"] = player["character"]["name"].strip().replace("'", "")

            game_obj.append(team_obj)


        team_1 = game_obj[0]
        team_2 = game_obj[1]
        Game.objects.update_or_create(
            match=match,
            team_1=Team.objects.get(external_id=team_1["id"]),
            team_2=Team.objects.get(external_id=team_2["id"]),
            game_id=game["sequenceNumber"],
            winning_team=Team.objects.get(external_id=winning_team),

            team_1_score=team_1["score"],
            team_1_side=team_1["side"],

            team_1_top_player_name=Player.objects.get(external_id=team_1["top_player"]).name,
            team_1_top_champion=team_1["top_champion"],
            team_1_jungle_player_name=Player.objects.get(external_id=team_1["jungle_player"]).name,
            team_1_jungle_champion=team_1["jungle_champion"],
            team_1_mid_player_name=Player.objects.get(external_id=team_1["mid_player"]).name,
            team_1_mid_champion=team_1["mid_champion"],
            team_1_bot_player_name=Player.objects.get(external_id=team_1["bottom_player"]).name,
            team_1_bot_champion=team_1["bottom_champion"],
            team_1_support_player_name=Player.objects.get(external_id=team_1["support_player"]).name,
            team_1_support_champion=team_1["support_champion"],
            
            team_2_score=team_2["score"],
            team_2_side=team_2["side"],

            team_2_top_player_name=Player.objects.get(external_id=team_2["top_player"]).name,
            team_2_top_champion=team_2["top_champion"],
            team_2_jungle_player_name = Player.objects.get(external_id=team_2["jungle_player"]).name,
            team_2_jungle_champion = team_2["jungle_champion"],
            team_2_mid_player_name = Player.objects.get(external_id=team_2["mid_player"]).name,
            team_2_mid_champion = team_2["mid_champion"],
            team_2_bot_player_name = Player.objects.get(external_id=team_2["bottom_player"]).name,
            team_2_bot_champion = team_2["bottom_champion"],
            team_2_support_player_name = Player.objects.get(external_id=team_2["support_player"]).name,
            team_2_support_champion = team_2["support_champion"],
        )


def get_and_save_player_metadata(match_metadata):
    for team in match_metadata["teams"]:
        for player in team["players"]:
            if Player.objects.filter(external_id=player["id"]).exists():
                #print("Player with id ", player["id"], " already exists")
                continue

            Player.objects.create(
                team=Team.objects.get(external_id=team["id"]),
                name=player["name"],
            )

            continue

            player_fields = graphql_utils.make_request(
                graphql_utils.GRAPHQL_CENTRAL_DATA_API_URL,
                graphql_queries.GET_PLAYER,
                {"player_id": player["id"]},
            )

            default_values = {
                "team": Team.objects.get(external_id=team["id"]),
                "name": player["name"],
            }

            roles = player_fields["player"].get("roles", [])

            print(player_fields)
            print("roles", roles)
            print("roles", len(roles))

            if len(roles) > 0 and roles[0]["name"] != 'none':
                role = roles[0]

                print(role)

                default_values.update({
                    "role": role["name"],
                    "role_id": role["id"],
                })

                # Only create or update if a role exists
                player_obj, created = Player.objects.update_or_create(
                    external_id=player["id"],  # lookup field
                    defaults=default_values
                )

                print("player_obj", player_obj)

            else:
                print("Saving player ", player)
                # Only create or update if a role exists
                player_obj, created = Player.objects.update_or_create(
                    external_id=player["id"],  # lookup field
                    defaults=default_values
                )

            # player_obj, created = Player.objects.update_or_create(
            #     external_id=player["id"],  # lookup field
            #     defaults=default_values
            # )
            #
            # if not player_fields["player"]["roles"]:
            #     Player.objects.filter(id=player["id"]).get_or_create(
            #         external_id=player["id"],
            #         team_id=player_fields["player"]["team"]["id"],
            #         name=player["name"],
            #     )
            #
            # else:
            #     Player.objects.filter(id=player["id"]).update_or_create(
            #         external_id=player["id"],
            #         role=player_fields["player"]["roles"][0]["name"],
            #         role_id=player_fields["player"]["roles"][0]["id"],
            #     )

def get_player_by_role(player_ids, role):
    print("player_ids", player_ids, role)
    return Player.objects.filter(
            external_id__in=player_ids,
            role=role,
        ).first()

# Define tiered decay factors based on distance (tweak values to taste)
def tiered_proximity(distance):
    if distance < 2000:
        decay = 0.0002   # slow decay for very close players
    elif distance < 5000:
        decay = 0.0004   # moderate decay for medium distance
    else:
        decay = 0.0006   # fast decay for far players
    return np.exp(-decay * distance)

def calculate_player_events(match, match_metadata):
    match_events = Event.objects.filter(match=match).values()

    event_objects = []

    for match_event in match_events:
        event_data = match_event["event_data"]
        occured_at = match_event["occured_at"]
        for event in event_data["events"]:
            event_type = event["type"]
            if event_type == "player-used-item":
                if DEBUG:
                    print(event["actor"]["state"]["name"], " used item ", event["target"]["id"], " @ ", occured_at)
                if event["target"]["id"] in WARD_ITEM_IDS:
                    match_frame = Frame.objects.filter(
                        match=match,
                        updated_at__gt=(occured_at)
                    ).values_list("raw_payload", flat=True).first()

                    games = match_frame["seriesState"]["games"]
                    game_time = games[len(games)-1]["clock"]["currentSeconds"]
                    player_id = Player.objects.filter(external_id=event["actor"]["id"]).values_list("id", flat=True).first()
                    game_id = games[len(games)-1]["sequenceNumber"]

                    player_frame = PlayerFrames.objects.filter(
                        match=match,
                        game_id=game_id,
                        game_time=game_time,
                        player_id=player_id,
                    ).values().first()

                    event_objects.append(PlayerEvents(
                        match=match,
                        player_id=player_id,
                        game_time=game_time,
                        game_id=game_id,
                        event_name="player_placed_ward",
                        event_type=event_type,
                        event_action="ward",
                        event_data=WARD_ITEM_IDS[event["target"]["id"]],
                        position_x=player_frame["position_x"],
                        position_y=player_frame["position_y"],
                    ))

    PlayerEvents.objects.bulk_create(event_objects)

                    # match_frame = Frame.objects.filter(
                    #     match=match,
                    #     updated_at__gt=(occured_at)
                    # ).values().first()
                    # games = match_frame["raw_payload"]["seriesState"]["games"]
                    # print(games)
                    # print(games[len(games)-1]["clock"]["currentSeconds"])
                    # print(player_event)
                    # print(event["actor"]["state"]["name"], " warded ", event["target"]["id"], " @ ", occured_at)
            # for event in event_data["event_data"]:
            #     print(event)
            #     print(event["action"])
            #     if event["action"] == "used":
            #         print(event)
        # print(event)
        # print(event)

def calculate_jungle_proximity(match, match_metadata):
    for game in match_metadata["last_live_series_state"]["games"]:
        print("Calculating jungle proximity for game", game["sequenceNumber"])
        sequence_number = game["sequenceNumber"]

        for team in game["teams"]:
            obj = []
            gold_diff_obj = []
            players = team["players"]
            player_ids = [p["id"] for p in players if "character" in p]
            top = get_player_by_role(player_ids, league_utils.TOP_ROLE)
            jungler = get_player_by_role(player_ids, league_utils.JUNGLE_ROLE)
            mid = get_player_by_role(player_ids, league_utils.MID_ROLE)
            bot = get_player_by_role(player_ids, league_utils.BOT_ROLE)
            support = get_player_by_role(player_ids, league_utils.SUPPORT_ROLE)

            avg_top_proximity = 0
            avg_mid_proximity = 0
            avg_bot_proximity = 0
            avg_support_proximity = 0

            player_mapping = {
                int(top.id): "top",
                int(mid.id): "mid",
                int(bot.id): "bot",
                int(support.id): "support",
            }

            #print("player_mapping=", player_mapping)

            game_time = 0
            if jungler:
                #print("game_time=", game_time)
                while game_time < game["clock"]["currentSeconds"]:
                    player_frames = PlayerFrames.objects.filter(
                        match=match,
                        game_id=sequence_number,
                        player_id__in = [top.id, jungler.id, mid.id, bot.id, support.id],
                        game_time__range=(game_time, game_time+30) #0-30, 31-60, 61-90
                    ).values("game_time", "player_id", "position_x", "position_y", "gold")  # <-- values() returns dicts

                    data_frame = pandas.DataFrame.from_records(player_frames)

                    if data_frame.empty and not player_frames:
                        print(f"No data for frames {game_time} till {game_time + 30} ")
                        print([top.external_id, jungler.external_id, mid.external_id, bot.external_id, support.external_id])
                        print("player_frames", player_frames)

                        game_time += 30

                        continue

                    jungler_df = data_frame[
                        data_frame["player_id"] == int(jungler.id)
                    ].set_index("game_time")[["position_x", "position_y"]]

                    if DEBUG:
                        print("jungle_df=", jungler_df)

                    others_dataframe = data_frame[data_frame["player_id"] != int(jungler.id)]

                    if DEBUG:
                        print("others_dataframe=", others_dataframe)

                    merged = others_dataframe.merge(jungler_df, left_on="game_time", right_index=True, suffixes=("", "_ref"))

                    if DEBUG:
                        print("merged=", merged)

                    #max_distance = np.sqrt(dx ** 2 + dy ** 2)  # diagonal length of the map
                    #max_distance = max_distance / 3
                    max_distance = np.sqrt((15000 - 7500) ** 2 + (14700 - 7200) ** 2)

                    merged["distance"] = np.sqrt(
                        (merged["position_x"] - merged["position_x_ref"]) ** 2 +
                        (merged["position_y"] - merged["position_y_ref"]) ** 2
                    )

                    # merged["proximity"] = (max_distance - merged["distance"]) / max_distance
                    #merged["proximity"] = 1 / (merged["distance"] + 1e-6)
                    # decay_factor = 0.0005  # tweak to taste
                    # merged["proximity"] = np.exp(-decay_factor * merged["distance"])
                    #merged["proximity"] = merged["proximity"] * 100

                    # Apply to the DataFrame
                    merged["proximity"] = merged["distance"].apply(tiered_proximity)
                    merged["proximity"] = merged["proximity"] * 100

                    #print("merged=", merged)

                    result = merged.groupby("player_id")["proximity"].mean().reset_index()
                    #print("result=", result)

                    result["role"] = result["player_id"].map(player_mapping)

                    distance_by_player_id = dict(zip(result["player_id"], result["proximity"]))

                    if DEBUG:
                        print(distance_by_player_id)

                    # print("distance_by_player_id=", distance_by_player_id)

                    # JungleProximity.objects.create(
                    #     match=match,
                    #     team_id=match_metadata["teams"][0]["id"],
                    #     game_sequence_number=sequence_number,
                    #     game_time=game_time,
                    #     jungle_player=jungler,
                    #     top_proximity=distance_by_player_id[int(top.external_id)],
                    #     mid_proximity=distance_by_player_id[int(mid.external_id)],
                    #     bot_proximity=distance_by_player_id[int(bot.external_id)],
                    #     support_proximity=distance_by_player_id[int(support.external_id)],
                    # )
                    game_time += 30

                    #print(teams)

                    avg_division = game_time / 30.0

                    avg_top_proximity += distance_by_player_id[int(top.id)]
                    avg_mid_proximity += distance_by_player_id[int(mid.id)]
                    avg_bot_proximity += distance_by_player_id[int(bot.id)]
                    avg_support_proximity += distance_by_player_id[int(support.id)]

                    obj.append(JungleProximity(
                        match=match,
                        team_id=match_metadata["team_external_ids"][team["id"]], # TODO: Teams.id is external_id in Teams table
                        game_sequence_number=sequence_number,
                        game_time=game_time,
                        jungle_player=jungler,
                        top_proximity=distance_by_player_id[int(top.id)],
                        mid_proximity=distance_by_player_id[int(mid.id)],
                        bot_proximity=distance_by_player_id[int(bot.id)],
                        support_proximity=distance_by_player_id[int(support.id)],
                        avg_top_proximity=avg_top_proximity / avg_division,
                        avg_mid_proximity=avg_mid_proximity / avg_division,
                        avg_bot_proximity=avg_bot_proximity / avg_division,
                        avg_support_proximity=avg_support_proximity / avg_division,
                    ))

                    net_worth=0

                    for player in player_frames:
                        # print(player)
                        net_worth += player["gold"]

                    gold_diff_obj.append(GoldDifference(
                        match=match,
                        team_id=match_metadata["team_external_ids"][team["id"]],
                        game_sequence_number=sequence_number,
                        game_time=game_time,
                        net_worth=net_worth,
                    ))

            #print(obj)
            JungleProximity.objects.bulk_create(obj)
            GoldDifference.objects.bulk_create(gold_diff_obj)

# def calculate_gold_difference(match, match_metadata):
#     teams = match["teams"]
#
#     for game in match_metadata["last_live_series_state"]["games"]:
#         print("Calculating gold difference for game", game["sequenceNumber"])
#         sequence_number = game["sequenceNumber"]
#         player_frames = PlayerFrames.objects.filter(
#             match=match,
#             game_id=sequence_number,
#         )
#
#         foreach player_frame in player_frames:
def calculate_objective_events(match, match_metadata):
    match_events = Event.objects.filter(match=match).order_by("id").values()

    objective_types = {
        'player-killed-ATierNPC',
        'player-killed-STierNPC',
        'game-respawned-ATierNPC',
        'game-respawned-STierNPC',
    }

    objective_event_object = []

    active_objectives  = {}

    for match_event in match_events:
        occured_at = match_event["occured_at"]
        for event in match_event["event_data"]["events"]:
            # TODO:
            if event["type"] in objective_types:
                print("event-action")
                # print(event['type'])
                # print("occured_at")
                # print(occured_at)
                # print("match")
                # print(match)

                #TODO : Check if it's respawn or kill
                match_frame = Frame.objects.filter(
                    match=match_event["match_id"],
                    updated_at__gt=occured_at
                ).values_list("raw_payload", flat=True).first()
                # print("match_frame")
                # print(match_frame)

                game_time = match_frame["seriesState"]["games"][len(match_frame["seriesState"]["games"]) - 1]["clock"]["currentSeconds"]

                # Respawn event
                if event['action'] == 'respawned' and 'game-respawned' in event["type"]:
                    print(f"{event["target"]["id"]} has spawned")

                    for team in match_metadata["teams"]:
                        key = (event["target"]["id"], team["name"])
                        team_stats = (
                            PlayerFrames.objects
                            .filter(
                                match_id=match_event["match_id"],
                                game_id=event['actor']['state']['sequenceNumber'],
                                player__team__name=team["name"],
                                game_time__gte=game_time,
                            )
                            .values('game_time')
                            .annotate(
                                total_gold=Sum('gold'),
                                total_xp=Sum('experience'),
                                total_kills=Sum('kills'),
                                total_deaths=Sum('deaths'),
                            )
                            .order_by('game_time')
                        ).first()

                        active_objectives[key] = {
                            'respawn_time': team_stats["game_time"],
                            'sequence_number': event['actor']['state']['sequenceNumber'],
                            'total_gold' : team_stats["total_gold"],
                            'total_xp' : team_stats["total_xp"],
                            'total_kills' : team_stats["total_kills"],
                            'total_deaths' : team_stats["total_deaths"],
                        }

                        print(f"Added {active_objectives} to active objectives")

                # Killed Event
                if event['action'] == 'killed' and 'player-killed' in event["type"]:
                    for team in match_metadata["teams"]:

                        killed = 0
                        if team["id"] in event["actor"]["state"]["teamId"]:
                            print(f"{team["name"]} killed {event["target"]["id"]}")
                            killed = 1
                        else:
                            print(f"{team["name"]} lost objective {event["target"]["id"]}")

                        key = (event["target"]["id"], team["name"])

                        if key not in active_objectives:
                            print(f"Unable to find active objective for team {team['name']} for event {event['target']['id']}")

                        # TODO : Check if it's respawn or kill
                        match_frame = Frame.objects.filter(
                            match=match_event["match_id"],
                            updated_at__gt=occured_at
                        ).values_list("raw_payload", flat=True).first()
                        # print("match_frame")
                        # print(match_frame)

                        game_time = match_frame["seriesState"]["games"][len(match_frame["seriesState"]["games"]) - 1]["clock"]["currentSeconds"]

                        team_stats = (
                            PlayerFrames.objects
                            .filter(
                                match_id=match_event["match_id"],
                                game_id=active_objectives[key]["sequence_number"],
                                player__team__name=team["name"],
                                game_time__gte=game_time,
                            )
                            .values('game_time')
                            .annotate(
                                total_gold=Sum('gold'),
                                total_xp=Sum('experience'),
                                total_kills=Sum('kills'),
                                total_deaths=Sum('deaths'),
                            )
                            .order_by('game_time')
                        ).first()

                        print("active_objective found")
                        print(f"calculating {active_objectives[key]} to active objective")
                        print("team_stats")
                        print(f"{team_stats}")

                        # objective_event_object.append(
                        ObjectiveEvents.objects.create(
                            match_id=match_event["match_id"],
                            team_id=match_metadata["team_external_ids"][team["id"]][0]["id"],
                            value=killed,
                            objective_name=event["target"]["id"],
                            objective_type=event["target"]["type"],
                            objective_sequence_number=active_objectives[key]["sequence_number"],
                            game_time=team_stats["game_time"],
                            alive_time=team_stats["game_time"] - active_objectives[key]['respawn_time'],
                            gold_difference=team_stats["total_gold"] - active_objectives[key]['total_gold'],
                            xp_difference=team_stats["total_xp"] - active_objectives[key]['total_xp'],
                            kills_difference=team_stats["total_kills"] - active_objectives[key]['total_kills'],
                            deaths_difference=team_stats["total_deaths"] - active_objectives[key]['total_deaths'],
                        )

                        active_objectives.pop(key)
                        # )

        # ObjectiveEvents.objects.bulk_create(objective_event_object)


                # TODO Get gold value at game_time, game_time-30 and game_time-60

                #TODO: Save values into table for gold, xp & objective_value / objective_killed 1 or 0

                #TODO Create models.py for table to hold objective_events?

def save_match_data(match: Match, match_data):
    for team in match_data['teams']:
        if team["id"] == match.team_1.external_id:
            match.team_1_score = team["score"]

        if team["id"] == match.team_2.external_id:
            match.team_2_score = team["score"]

        if team['won']:
            match.winning_team_id = Team.objects.get(external_id=team['id'])

    match.save()

def save_game_data(match: Match, games: dict):
    for game in games['games']:

        game_obj = []

        for team in game["teams"]:

            team_obj = {"id": team["id"], "side": team["side"]}

            if team["won"]:
                winning_team = team["id"]
                team_obj["score"] = 1
            else:
                team_obj["score"] = 0

            # for player in team["players"]:
            #     player_role = Player.objects.filter(external_id=player["id"]).values("role")[0]
            #
            #     if "character" not in player:
            #         print("Player", player["id"], "has no character")
            #         print(team["players"])
            #         continue

                # team_obj[player_role["role"] + "_player"] = player["id"]
                # team_obj[player_role["role"] + "_champion"] = player["character"]["name"].strip().replace("'", "")

            game_obj.append(team_obj)

        team_1 = game_obj[0]
        team_2 = game_obj[1]
        Game.objects.update_or_create(
            match=match,
            team_1=Team.objects.get(external_id=team_1["id"]),
            team_2=Team.objects.get(external_id=team_2["id"]),
            game_id=game["sequenceNumber"],
            winning_team=Team.objects.get(external_id=winning_team),

            team_1_score=team_1["score"],
            team_1_side=team_1["side"],

            # team_1_top_player_name=Player.objects.get(external_id=team_1["top_player"]).name,
            # team_1_top_champion=team_1["top_champion"],
            # team_1_jungle_player_name=Player.objects.get(external_id=team_1["jungle_player"]).name,
            # team_1_jungle_champion=team_1["jungle_champion"],
            # team_1_mid_player_name=Player.objects.get(external_id=team_1["mid_player"]).name,
            # team_1_mid_champion=team_1["mid_champion"],
            # team_1_bot_player_name=Player.objects.get(external_id=team_1["bottom_player"]).name,
            # team_1_bot_champion=team_1["bottom_champion"],
            # team_1_support_player_name=Player.objects.get(external_id=team_1["support_player"]).name,
            # team_1_support_champion=team_1["support_champion"],

            team_2_score=team_2["score"],
            team_2_side=team_2["side"],

            # team_2_top_player_name=Player.objects.get(external_id=team_2["top_player"]).name,
            # team_2_top_champion=team_2["top_champion"],
            # team_2_jungle_player_name=Player.objects.get(external_id=team_2["jungle_player"]).name,
            # team_2_jungle_champion=team_2["jungle_champion"],
            # team_2_mid_player_name=Player.objects.get(external_id=team_2["mid_player"]).name,
            # team_2_mid_champion=team_2["mid_champion"],
            # team_2_bot_player_name=Player.objects.get(external_id=team_2["bottom_player"]).name,
            # team_2_bot_champion=team_2["bottom_champion"],
            # team_2_support_player_name=Player.objects.get(external_id=team_2["support_player"]).name,
            # team_2_support_champion=team_2["support_champion"],
        )

def save_draft(match: Match, data):
    for game in data['games']:
        side_selection = {game['teams'][0]['id']: game['teams'][0]['side'], game['teams'][1]['id']: game['teams'][1]['side']}
        for draft_action in game['draftActions']:
            champion, _ = Champion.objects.get_or_create(
                id=draft_action['draftable']["id"],
                defaults={"name": draft_action['draftable']["name"]}
            )

            DraftAction.objects.get_or_create(
                game=Game.objects.get(match_id=match.id, game_id=game["sequenceNumber"]),
                sequence_number=int(draft_action["sequenceNumber"]),
                action_type=draft_action["type"],
                team_side=side_selection[draft_action["drafter"]["id"]],  # if available in JSON
                champion=champion,
                drafter_id=draft_action["drafter"]["id"]
            )


class Command(BaseCommand):
    help = "Run post-game draft analysis for a match"

    def handle(self, *args, **options):
        draft_matches = Match.objects.filter(state="SERIES_FETCHED_FOR_DRAFT")
        total_matches = draft_matches.count()
        print(f"Found {total_matches} matches to process.")

        processed_count = 0
        skipped_count = 0
        empty_count = 0
        error_count = 0

        for i, match in enumerate(draft_matches, 1):
            progress_prefix = f"[{i}/{total_matches}]"
            try:
                # Check if all games already have 20 draft actions
                games = match.games.all()
                if games.exists() and match.team_1_score is not None and match.team_2_score is not None:
                    expected_games = match.team_1_score + match.team_2_score
                    if games.count() == expected_games:
                        all_drafts_complete = True
                        for game in games:
                            if game.draft_actions.count() < 20:
                                all_drafts_complete = False
                                break
                        if all_drafts_complete:
                            print(f"{progress_prefix} Skipping match {match.external_id} as it already has all draft actions.")
                            match.state = "DRAFT_ACTIONS_FETCHED"
                            match.save()
                            skipped_count += 1
                            continue

                print(f"{progress_prefix} Getting data for match {match}")
                series_state = graphql_utils.make_request(
                    graphql_utils.GRAPHQL_LIVE_DATA_FEED_SERIES_STATE_API_URL,
                    graphql_queries.GET_DRAFT,
                    {"series_id": match.external_id},
                    'draft'
                )

                if not series_state:
                    print(f"{progress_prefix} No series data for match {match.external_id}! Skipping. (See above for details)")
                    match.state = "DRAFT_SERIES_STATE_EMPTY"
                    match.save()
                    empty_count += 1
                    continue

                save_match_data(match, series_state['seriesState'])

                get_and_save_player_metadata(series_state['seriesState'])

                save_game_data(match, series_state['seriesState'])

                save_draft(match, series_state['seriesState'])

                match.state = "DRAFT_ACTIONS_FETCHED"
                match.save()

                num_games = len(series_state['seriesState'].get('games', []))
                num_draft_actions = sum(len(g.get('draftActions', [])) for g in series_state['seriesState'].get('games', []))
                print(f"{progress_prefix} Successfully saved {num_games} games and {num_draft_actions} draft actions for match {match.external_id}")
                processed_count += 1

                # Small delay between matches to respect rate limits
                time.sleep(1)

            except Exception as e:
                print(f"{progress_prefix} Error processing match {match.external_id}: {e}")
                traceback.print_exc()
                error_count += 1

        print(f"\nProcessing finished.")
        print(f"Total: {total_matches}")
        print(f"Processed: {processed_count}")
        print(f"Skipped (Already complete): {skipped_count}")
        print(f"Empty (No API data): {empty_count}")
        print(f"Errors: {error_count}")

