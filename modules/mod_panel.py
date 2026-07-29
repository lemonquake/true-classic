"""
True Classic Bot - Moderation Control Panel Module
Author: Aljay Leodones
Organization: True Classic
"""

import os
import discord
from discord.ext import commands
from discord import app_commands
import config
from utils import embed_builder

class ModPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="summon", description="Summon the True Classic Mod Panel")
    async def summon(self, interaction: discord.Interaction):
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        else:
            await interaction.response.send_message("This command can only be used within a guild.", ephemeral=True)
            return

        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        print(f"[Command] /summon executed by {interaction.user} ({interaction.user.id}) in #{interaction.channel.name}")
        
        view = ModPanelView(self.bot)
        embed = await view.get_panel_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="reload", description="Hot-reload all bot modules and load updates")
    async def reload_cogs(self, interaction: discord.Interaction):
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        reloaded_modules, errors = await reload_bot_system(self.bot)
        
        if errors:
            err_msg = "\n".join(errors)
            embed = embed_builder.warning_embed(
                "Bot Refreshed with Warnings",
                f"Reloaded {len(reloaded_modules)} module(s), but encountered errors:\n```\n{err_msg}\n```"
            )
        else:
            embed = embed_builder.success_embed(
                "Bot Refreshed & Updated",
                f"Successfully hot-reloaded **{len(reloaded_modules)}** module(s):\n" + "\n".join([f"• `{m}`" for m in reloaded_modules])
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

async def reload_bot_system(bot: commands.Bot) -> tuple[list[str], list[str]]:
    modules = ["modules.mod_panel", "modules.onboarding", "modules.member_report", "modules.scheduled_messages"]
    reloaded = []
    errors = []
    
    for mod in modules:
        try:
            await bot.reload_extension(mod)
            reloaded.append(mod)
            print(f"[System] Hot-reloaded extension: {mod}")
        except Exception as e:
            errors.append(f"{mod}: {str(e)}")
            print(f"[Error] Failed to reload {mod}: {e}")

    try:
        await bot.tree.sync()
        print("[System] Re-synced slash commands tree.")
    except Exception as e:
        errors.append(f"tree.sync: {str(e)}")

    # Re-register persistent view
    bot.add_view(ModPanelView(bot))
    return reloaded, errors

class ModPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # Persistent view across bot restarts
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to use this panel."),
                ephemeral=True
            )
            return False
        return True

    async def get_panel_embed(self):
        latency = round(self.bot.latency * 1000)
        template_count = 0
        if os.path.exists("templates"):
            template_count = len([f for f in os.listdir("templates") if f.endswith(".json")])

        pending_scheduled = 0
        try:
            rows = await self.bot.database.fetchall("SELECT COUNT(*) as cnt FROM scheduled_messages WHERE status = 'pending'")
            if rows:
                pending_scheduled = rows[0]["cnt"]
        except Exception:
            pass
            
        embed = embed_builder.base_embed(
            title="True Classic • Control Panel",
            description="Select a module below to start. Persistent across bot restarts.",
            color=embed_builder.COLOR_BRAND
        )
        
        health_block = (
            "```ansi\n"
            f"✓ {'Database (SQLite)':<20} \u001b[0;32mONLINE\u001b[0m\n"
            f"✓ {'Gateway Latency':<20} \u001b[0;33m{latency}ms\u001b[0m\n"
            f"✓ {'Embed Templates':<20} \u001b[0;36m{template_count} Loaded\u001b[0m\n"
            f"✓ {'Pending Schedules':<20} \u001b[0;35m{pending_scheduled} Active\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🩺 System Health & Status", value=health_block, inline=False)
        embed.add_field(
            name="🛠️ Available Modules & Controls",
            value=(
                "**Embed Editor**: Compose multi-embed broadcasts with dynamic hydrators.\n"
                "**Member Onboarding**: Scan 30-day un-onboarded members & send deep-link DMs.\n"
                "**Member Report**: Deploy self-updating daily/weekly/monthly growth reports.\n"
                "**Scheduled Messages**: Schedule broadcasts with timezones, 5-min intervals & multi-channel targeting.\n\n"
                "🔄 **Update Panel**: Instantly refreshes panel state and live system metrics.\n"
                "🔄 **Reload Bot & Updates**: Hot-reloads all bot code, cogs, and slash commands without offline downtime."
            ),
            inline=False
        )
        return embed

    async def show_panel(self, interaction: discord.Interaction):
        embed = await self.get_panel_embed()
        if interaction.response.is_done():
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Embed Editor", style=discord.ButtonStyle.blurple, row=0, custom_id="mod_panel:embed_editor")
    async def embed_editor(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Embed Editor")
        from modules.embed_editor import EditorSession, EmbedEditorHubView
        session = EditorSession()
        hub_view = EmbedEditorHubView(session, self)
        
        await interaction.response.edit_message(
            embed=hub_view.get_hub_embed(),
            view=hub_view
        )

    @discord.ui.button(label="Member Onboarding", style=discord.ButtonStyle.success, row=0, custom_id="mod_panel:member_onboarding")
    async def member_onboarding(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Member Onboarding")
        from modules.onboarding import OnboardingHubView
        hub_view = OnboardingHubView(self, self.bot)
        
        embed = embed_builder.info_embed(
            "👋 Member Onboarding Hub",
            "Scan for un-onboarded new members and send welcome messages."
        )
        await interaction.response.edit_message(embed=embed, view=hub_view)

    @discord.ui.button(label="Member Report", style=discord.ButtonStyle.secondary, row=0, custom_id="mod_panel:member_report")
    async def member_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Member Report")
        from modules.member_report import MemberReportHubView
        hub_view = MemberReportHubView(self.bot, self)
        embed = await hub_view.get_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=hub_view)

    @discord.ui.button(label="📅 Scheduled Messages", style=discord.ButtonStyle.blurple, row=0, custom_id="mod_panel:scheduled_messages")
    async def scheduled_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Scheduled Messages")
        from modules.scheduled_messages import ScheduledMessagesHubView
        hub_view = ScheduledMessagesHubView(self.bot, self)
        embed = await hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=hub_view)

    @discord.ui.button(label="🔄 Update Panel", style=discord.ButtonStyle.secondary, row=1, custom_id="mod_panel:update_panel")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} updated the control panel")
        await self.show_panel(interaction)

    @discord.ui.button(label="🔄 Reload Bot & Updates", style=discord.ButtonStyle.success, row=1, custom_id="mod_panel:reload_bot")
    async def reload_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} triggered bot reload & updates")
        await interaction.response.defer(ephemeral=True)
        
        reloaded, errors = await reload_bot_system(self.bot)
        
        if errors:
            err_str = "\n".join(errors)
            msg = f"Reloaded {len(reloaded)} modules, but encountered errors:\n```\n{err_str}\n```"
            await interaction.followup.send(embed=embed_builder.warning_embed("Bot Reloaded with Warnings", msg), ephemeral=True)
        else:
            msg = f"Successfully hot-reloaded **{len(reloaded)}** module(s) and re-synced commands:\n" + "\n".join([f"• `{m}`" for m in reloaded])
            await interaction.followup.send(embed=embed_builder.success_embed("Bot Code & Updates Loaded", msg), ephemeral=True)

        await self.show_panel(interaction)

async def setup(bot):
    await bot.add_cog(ModPanelCog(bot))
