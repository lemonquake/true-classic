"""
True Classic Bot - Main Entry Point
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

import math
import datetime
import discord
from discord.ext import commands
import config
from database import Database

class TrueClassicBot(commands.Bot):
    def __init__(self):
        # Set up necessary intents
        intents = discord.Intents.default()
        intents.members = True  # Required for onboarding scanning and join reconciliation
        intents.message_content = True  # Message content intent for engagement tracking

        super().__init__(command_prefix="!", intents=intents)
        self.database = Database()
        self.start_time = datetime.datetime.now(datetime.timezone.utc)  # Surfaced as panel uptime
        self._panels_restored = False

    async def setup_hook(self):
        # 1. Connect database & run table migrations
        await self.database.connect()
        
        # 2. Load extensions
        extensions = [
            "modules.mod_panel",
            "modules.onboarding",
            "modules.member_report",
            "modules.scheduled_messages",
            "modules.summarizer"
        ]
        for ext in extensions:
            await self.load_extension(ext)
            print(f"[System] Loaded extension: {ext}")
        
        # 3. Register persistent views
        from modules.mod_panel import ModPanelView
        self.add_view(ModPanelView(self))
        print("[System] Registered persistent view: ModPanelView")

    async def close(self):
        await self.database.close()
        await super().close()

    async def on_ready(self):
        print("========================================")
        print(f"Logged in as: {self.user.name} ({self.user.id})")
        print(f"Status: Online")
        # latency is NaN until the first heartbeat ack; round() would raise and abort on_ready.
        print(f"Latency: {'pending' if math.isnan(self.latency) else str(round(self.latency * 1000)) + 'ms'}")
        
        if not self.intents.members:
            print("[Warning] Server Members Intent is disabled. Onboarding scan will not work.")
        else:
            print("[System] Server Members Intent is enabled.")
            
        print("----------------------------------------")
        
        # Sync slash commands globally
        try:
            print("[System] Syncing slash commands globally...")
            synced = await self.tree.sync()
            print(f"[System] Successfully synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"[Error] Failed to sync command tree: {str(e)}")

        # Revive every previously summoned Mod Panel with fresh state. Guarded so a
        # gateway reconnect (which re-fires on_ready) doesn't re-edit every panel.
        if not self._panels_restored:
            self._panels_restored = True
            from modules.mod_panel import restore_panels
            try:
                restored, pruned, failed = await restore_panels(self)
                print(f"[System] Mod Panels restored: {restored} live, {pruned} pruned, {failed} failed.")
            except Exception as e:
                print(f"[Error] Failed to restore Mod Panels: {str(e)}")

        print("========================================")

def main():
    if not config.DISCORD_TOKEN:
        print("[Critical Error] DISCORD_TOKEN is missing in the configuration. Please check your .env file.")
        return
        
    bot = TrueClassicBot()
    bot.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()
