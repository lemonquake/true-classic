"""
True Classic Bot - Configuration Management
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

import os
from dotenv import load_dotenv

# Bot Metadata
BOT_PREPARED_FOR = "True Classic"
BOT_ORIGINALITY_NOTE = "The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc"

# Load variables from .env file

# Load variables from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
AUTHORIZED_ROLES_RAW = os.getenv("AUTHORIZED_ROLES", "")

ONBOARDING_CHANNEL_ID = int(os.getenv("ONBOARDING_CHANNEL_ID", "0")) if os.getenv("ONBOARDING_CHANNEL_ID", "").isdigit() else 0
INTRODUCTIONS_CHANNEL_ID = int(os.getenv("INTRODUCTIONS_CHANNEL_ID", "0")) if os.getenv("INTRODUCTIONS_CHANNEL_ID", "").isdigit() else 0

# Destination channel for Summarizer reports (override via .env if it ever moves)
SUMMARY_REPORT_CHANNEL_ID = (
    int(os.getenv("SUMMARY_REPORT_CHANNEL_ID"))
    if os.getenv("SUMMARY_REPORT_CHANNEL_ID", "").isdigit()
    else 1521574949238603906
)

# Parse authorized roles as list of integers
AUTHORIZED_ROLES = []
if AUTHORIZED_ROLES_RAW:
    for r in AUTHORIZED_ROLES_RAW.split(","):
        r_str = r.strip()
        if r_str.isdigit():
            AUTHORIZED_ROLES.append(int(r_str))
