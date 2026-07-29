"""
True Classic Bot - Inner Group Channel Roster
Author: Aljay Leodones
Organization: True Classic

Single source of truth for the Inner Circle DM's and Academy DM's channel maps.
Add / remove creators here only -- the Summarizer module reads from this file.
Format: "creator username": channel_id
"""

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

GROUPS = {
    "inner_circle": {
        "key":      "inner_circle",
        "label":    "Inner Circle DM's",
        "short":    "Inner Circle",
        "emoji":    "🎯",
        "slug":     "inner_circle",
        "channels": INNER_CIRCLE_CHANNELS,
    },
    "academy": {
        "key":      "academy",
        "label":    "Academy DM's",
        "short":    "Academy",
        "emoji":    "🎓",
        "slug":     "academy",
        "channels": ACADEMY_CHANNELS,
    },
}


def get_group(group_key: str) -> dict | None:
    return GROUPS.get(group_key)


def all_group_keys() -> list[str]:
    return list(GROUPS.keys())
