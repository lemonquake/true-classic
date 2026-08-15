"""
True Classic Bot - Summarizer Scan Targets
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc

Single source of truth for what the Summarizer scans.

The program now runs out of one shared public channel (#community-chat), so the
Summarizer scans that channel and builds one care card per creator who posted in
it -- instead of one card per private DM channel.

Two scan modes are supported:
  "shared_channel" -- read one channel, split it per creator author.
  "channel_roster" -- read a fixed map of {creator: channel_id}, one card each.

The per-creator DM rosters below are retired: they are kept for reference (and so a
group can be restored in one line) but nothing scans them while GROUPS excludes them.
"""

import config

# --- retired: private DM channel rosters -----------------------------------
# Not scanned. Kept so the roster is not lost while the DM channels are wound down.
INNER_CIRCLE_CHANNELS = {
    "wackytimes0":            1506337798406275263,
    "tylerhennis":            1497349839904837753,
    "rileyreviews24":         1497363339599282246,
    "theebomeister":          1497349623034155128,
    "raddstore":              1501701736996274318,
    "tanner_kingery_":        1497366502201102388,
    "shaverdude":             1497364112798257325,
    "giozuppardo":            1497354224646754454,
    "markymark12":            1497356695737991259,
    "byblakejames":           1497360197751144509,
    "big1500reviews":         1497358215090802708,
    "natefindss":             1497361413696520293,
    "selfimprovementdeals":   1497368339993985026,
    "bricesmithhh":           1497369021023256726,
    "adventurereviewga":      1501975972956864542,
    "somomama":               1502350239984521296,
    "shoprightessentials":    1502355115707863231,
    "elvoa":                  1502358832028979250,
    "cryptodeals-nutriwish":  1502383130206802061,
    "evansnydz":              1506340147514445894,
    "benplunkett":            1509972775429996599,
    "johnbshop0":             1511060668734902393,
}

ACADEMY_CHANNELS = {
    "dcfitness1":       1512462312177402008,
    "becomingbrandon":  1512464398567079977,
    "ilovenume":        1514258056848871495,
    "shakira":          1514338167845818623,
    "indigo":           1516137431009857596,
    "mike":             1516892281863671838,
    "alfredohae":       1520165900446072974,
    "johnnybiggio":     1524124599485333574,
    "_coach_chris_":    1524481791979946114,
}

# --- live scan targets ------------------------------------------------------

GROUPS = {
    "community": {
        "key":        "community",
        "label":      "Community",
        "short":      "Community",
        "emoji":      "💬",
        "slug":       "community",
        "mode":       "shared_channel",
        "channel_id": config.COMMUNITY_CHAT_CHANNEL_ID,
        # One entry so anything counting scan targets still reads 1 channel.
        "channels":   {config.COMMUNITY_CHAT_CHANNEL_NAME: config.COMMUNITY_CHAT_CHANNEL_ID},
    },
}

DEFAULT_GROUP_KEY = "community"


def get_group(group_key: str) -> dict | None:
    return GROUPS.get(group_key)


def all_group_keys() -> list[str]:
    return list(GROUPS.keys())


def default_group() -> dict:
    return GROUPS[DEFAULT_GROUP_KEY]
