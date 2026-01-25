# draft/encoding/constants.py

NUM_CHAMPIONS = 170          # update if needed
NUM_ROLES = 5               # TOP, JUNGLE, MID, ADC, SUPPORT
NUM_PHASES = 3              # EARLY / MID / LATE

SIDE_TO_IDX = {"blue": 0, "red": 1}
PHASE_TO_IDX = {"EARLY": 0, "MID": 1, "LATE": 2}
ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

DRAFT_PHASES = [
    ("blue", "ban"), ("red", "ban"),
    ("blue", "ban"), ("red", "ban"),
    ("blue", "ban"), ("red", "ban"),

    ("blue", "pick"),
    ("red", "pick"), ("red", "pick"),
    ("blue", "pick"), ("blue", "pick"),
    ("red", "pick"),

    ("red", "ban"), ("blue", "ban"),
    ("red", "ban"), ("blue", "ban"),

    ("red", "pick"),
    ("blue", "pick"), ("blue", "pick"),
    ("red", "pick"),
]