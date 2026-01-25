import os
import time
import json
from time import sleep

import requests
import time
from datetime import datetime, timedelta
from collections import deque
from django.core.management.base import BaseCommand
from django.db.models import Empty
from django.utils.dateparse import parse_datetime
from selenium.webdriver.common.devtools.v137.fetch import continue_request

from matches.models import Match, Frame, Player, Team
from pathlib import Path

last_updated = None

def load_query(name: str) -> str:
    graphql_dir = Path(__file__).resolve().parent.parent.parent / "graphql"
    with open(graphql_dir / name, "r", encoding="utf-8") as f:
        return f.read()

def save_player_data(data):
    for node in data['players']['edges']:
        print(node['node'])
        player_team = None
        role = None
        role_id = None

        if node['node']['team'] is not None:
            team_name = node['node']['team']['name']
            player_team, _ = Team.objects.get_or_create(
                name=team_name,
                external_id=node['node']['team']['id'],
            )

        if node['node']['roles']:
            role = node['node']['roles'][0]['name']
            role_id = node['node']['roles'][0]['id']


        Player.objects.update_or_create(
            name=node['node']['nickname'],
            external_id=node['node']['id'],
            team=player_team,
            role=role,
            role_id=role_id,
        )

def save_series_data(data):
    for node in data['allSeries']['edges']:
        print(node)
        team_1, _ = Team.objects.get_or_create(external_id=node["node"]["teams"][0]["baseInfo"]["id"], defaults={"name": node["node"]["teams"][0]["baseInfo"]["name"]})
        team_2, _ = Team.objects.get_or_create(external_id=node["node"]["teams"][1]["baseInfo"]["id"], defaults={"name": node["node"]["teams"][1]["baseInfo"]["name"]})

        if node['node'] is not None:
            Match.objects.get_or_create(
                external_id=node['node']['id'],
                defaults={
                    "start_time": parse_datetime(node['node']["startTimeScheduled"]),
                    "team_1": team_1,
                    "team_2": team_2,
                    "tournament": node['node']["tournament"]["name"],
                    "state": "SERIES_FETCHED_FOR_DRAFT",
                },
            )

class Command(BaseCommand):
    help = "Polling worker: query GraphQL for player data"

    def handle(self, *args, **options):
        graphql_url = os.getenv("GRAPHQL_CENTRAL_DATA")  # or use a REST GraphQL endpoint
        api_key = os.getenv("GRAPHQL_API_KEY")
        print(api_key)

        if not graphql_url or not api_key:
            self.stderr.write("GRAPHQL_WS_URL or GRAPHQL_API_KEY missing")
            return

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,  # adjust according to your API
        }
        
        query = load_query("get-all-series-for-draft.graphql")

        payload = {"query": query, "variables": {"endCursor": "PjMLC1oLC0ZFQk5DRwsLWgsL"}}
        resp = requests.post(graphql_url, headers=headers, json=payload)
        print("1")
        print(resp.json())

        data = resp.json()["data"]
        has_next_page = True
        total_count = data['allSeries']['totalCount']
        current_count = 0

        while has_next_page:
            save_series_data(data)
            current_count += 50
            print("currentCount:", current_count, " out of totalCount:", total_count)

            payload = {"query": query, "variables": {"endCursor": data['allSeries']['pageInfo']['endCursor']}}
            resp = requests.post(graphql_url, headers=headers, json=payload)
            data = resp.json()["data"]
            has_next_page = data['allSeries']['pageInfo']['hasNextPage']

            if current_count % 500 == 0:
                print("Sleeping...")
                sleep(120)
                print("Done Sleeping")

        save_series_data(data)