"""
True Classic Bot - Main Entry Point
Author: Aljay Leodones
Organization: True Classic
"""

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

    async def setup_hook(self):
        # 1. Connect database & run table migrations
        await self.database.connect()
        
        # 2. Load extensions
        extensions = [
            "modules.mod_panel",
            "modules.onboarding",
            "modules.member_report"
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
        print(f"Latency: {round(self.latency * 1000)}ms")
        
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
            
        print("========================================")

def main():
    if not config.DISCORD_TOKEN:
        print("[Critical Error] DISCORD_TOKEN is missing in the configuration. Please check your .env file.")
        return
        
    bot = TrueClassicBot()
    bot.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()
