"""
True Classic Bot - Configuration Management
Author: Aljay Leodones
Organization: True Classic
"""

import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
AUTHORIZED_ROLES_RAW = os.getenv("AUTHORIZED_ROLES", "")

ONBOARDING_CHANNEL_ID = int(os.getenv("ONBOARDING_CHANNEL_ID", "0")) if os.getenv("ONBOARDING_CHANNEL_ID", "").isdigit() else 0
INTRODUCTIONS_CHANNEL_ID = int(os.getenv("INTRODUCTIONS_CHANNEL_ID", "0")) if os.getenv("INTRODUCTIONS_CHANNEL_ID", "").isdigit() else 0

# Parse authorized roles as list of integers
AUTHORIZED_ROLES = []
if AUTHORIZED_ROLES_RAW:
    for r in AUTHORIZED_ROLES_RAW.split(","):
        r_str = r.strip()
        if r_str.isdigit():
            AUTHORIZED_ROLES.append(int(r_str))
