"""
True Classic Bot - Moderation Control Panel Module
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc

The control panel is fully persistent: every summoned panel message is recorded in
the `mod_panels` table, re-attached to a live view on boot, and re-rendered with
fresh metrics. A panel left sitting in a sub-module hub (Embed Editor, Summarizer,
etc.) is reset back to the dashboard on startup, so no panel message is ever dead.
"""

import os
import math
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import config
from utils import embed_builder

MODULE_EXTENSIONS = [
    "modules.mod_panel",
    "modules.onboarding",
    "modules.member_report",
    "modules.scheduled_messages",
    "modules.summarizer",
    "modules.quick_announcement",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_authorized_role(user) -> bool:
    roles = getattr(user, "roles", None)
    if not roles:
        return False
    user_roles = {role.id for role in roles}
    return any(role_id in user_roles for role_id in config.AUTHORIZED_ROLES)


def _format_uptime(started_at: datetime.datetime | None) -> str:
    if not started_at:
        return "unknown"
    delta = datetime.datetime.now(datetime.timezone.utc) - started_at
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ---------------------------------------------------------------------------
# Panel registry (persistence layer)
# ---------------------------------------------------------------------------

async def register_panel(bot: commands.Bot, guild_id: int, channel_id: int, message_id: int, user_id: int | None = None):
    """Record (or refresh) a panel message so it survives a bot restart."""
    try:
        await bot.database.execute(
            """
            INSERT INTO mod_panels (message_id, guild_id, channel_id, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                guild_id   = excluded.guild_id,
                channel_id = excluded.channel_id,
                updated_at = datetime('now')
            """,
            (message_id, guild_id, channel_id, user_id),
        )
    except Exception as e:
        print(f"[Mod Panel] Failed to register panel message {message_id}: {e}")


async def unregister_panel(bot: commands.Bot, message_id: int):
    try:
        await bot.database.execute("DELETE FROM mod_panels WHERE message_id = ?", (message_id,))
    except Exception as e:
        print(f"[Mod Panel] Failed to unregister panel message {message_id}: {e}")


async def get_registered_panels(bot: commands.Bot) -> list:
    try:
        return list(await bot.database.fetchall(
            "SELECT message_id, guild_id, channel_id FROM mod_panels ORDER BY created_at ASC"
        ))
    except Exception as e:
        print(f"[Mod Panel] Failed to read panel registry: {e}")
        return []


async def restore_panels(bot: commands.Bot) -> tuple[int, int, int]:
    """
    Re-hydrate every tracked panel message after a restart.

    Each message is edited with a fresh embed + a fresh persistent view, which also
    rescues panels that were left showing a (non-persistent) sub-module hub.
    Returns (restored, pruned, failed).
    """
    rows = await get_registered_panels(bot)
    restored = pruned = failed = 0

    for row in rows:
        message_id = row["message_id"]
        channel_id = row["channel_id"]

        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                await unregister_panel(bot, message_id)
                pruned += 1
                print(f"[Mod Panel] Pruned panel {message_id}: channel {channel_id} is gone or inaccessible.")
                continue
            except discord.HTTPException as e:
                failed += 1
                print(f"[Mod Panel] Could not fetch channel {channel_id}: {e}")
                continue

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await unregister_panel(bot, message_id)
            pruned += 1
            print(f"[Mod Panel] Pruned panel {message_id}: message was deleted.")
            continue
        except (discord.Forbidden, discord.HTTPException) as e:
            failed += 1
            print(f"[Mod Panel] Could not fetch panel message {message_id}: {e}")
            continue

        if bot.user and message.author.id != bot.user.id:
            await unregister_panel(bot, message_id)
            pruned += 1
            print(f"[Mod Panel] Pruned panel {message_id}: not authored by the bot.")
            continue

        view = ModPanelView(bot)
        embed = await view.get_panel_embed(getattr(channel, "guild", None))
        try:
            await message.edit(embed=embed, view=view)
            await register_panel(bot, row["guild_id"], channel_id, message_id)
            restored += 1
            print(f"[Mod Panel] Restored panel {message_id} in #{getattr(channel, 'name', channel_id)}")
        except discord.HTTPException as e:
            failed += 1
            print(f"[Mod Panel] Failed to restore panel {message_id}: {e}")

    return restored, pruned, failed


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------

async def reload_bot_system(bot: commands.Bot) -> tuple[list[str], list[str]]:
    reloaded = []
    errors = []

    for mod in MODULE_EXTENSIONS:
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

    # Re-register the persistent view using the freshly reloaded module, so the
    # class handling future button presses is the new code, not this stale one.
    try:
        from modules.mod_panel import ModPanelView as ReloadedPanelView
        bot.add_view(ReloadedPanelView(bot))
        print("[System] Re-registered persistent view: ModPanelView")
    except Exception as e:
        errors.append(f"add_view: {str(e)}")

    return reloaded, errors


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ModPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="summon", description="Summon the True Classic Mod Panel")
    async def summon(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used within a guild.", ephemeral=True)
            return

        if not has_authorized_role(interaction.user):
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        print(f"[Command] /summon executed by {interaction.user} ({interaction.user.id}) in #{interaction.channel.name}")

        view = ModPanelView(self.bot)
        embed = await view.get_panel_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

        # Track the message so it can be revived after a restart.
        try:
            message = await interaction.original_response()
            await register_panel(self.bot, interaction.guild.id, message.channel.id, message.id, interaction.user.id)
            print(f"[Mod Panel] Registered persistent panel message {message.id}")
        except Exception as e:
            print(f"[Mod Panel] Could not register summoned panel: {e}")

    @app_commands.command(name="reload", description="Hot-reload all bot modules and load updates")
    async def reload_cogs(self, interaction: discord.Interaction):
        if not has_authorized_role(interaction.user):
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        reloaded_modules, errors = await reload_bot_system(self.bot)
        restored, pruned, failed = await restore_panels(self.bot)

        summary = f"\n\n**Panels:** {restored} refreshed • {pruned} pruned • {failed} failed"

        if errors:
            err_msg = "\n".join(errors)
            embed = embed_builder.warning_embed(
                "Bot Refreshed with Warnings",
                f"Reloaded {len(reloaded_modules)} module(s), but encountered errors:\n```\n{err_msg}\n```{summary}"
            )
        else:
            embed = embed_builder.success_embed(
                "Bot Refreshed & Updated",
                f"Successfully hot-reloaded **{len(reloaded_modules)}** module(s):\n"
                + "\n".join([f"• `{m}`" for m in reloaded_modules])
                + summary
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Stop tracking a panel once its message is deleted."""
        if not self.bot.user or message.author.id != self.bot.user.id:
            return
        try:
            row = await self.bot.database.fetchone(
                "SELECT message_id FROM mod_panels WHERE message_id = ?", (message.id,)
            )
        except Exception:
            return
        if row:
            await unregister_panel(self.bot, message.id)
            print(f"[Mod Panel] Panel message {message.id} deleted — removed from registry.")


# ---------------------------------------------------------------------------
# Panel view
# ---------------------------------------------------------------------------

class ModPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # Persistent view across bot restarts
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not has_authorized_role(interaction.user):
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to use this panel."),
                ephemeral=True
            )
            return False
        return True

    # -- Live metrics -------------------------------------------------------

    async def _collect_metrics(self, guild: discord.Guild | None) -> dict:
        """Every metric is gathered defensively so one failure can't break a refresh."""
        m = {}

        # bot.latency is NaN until the first heartbeat ack, and round() rejects NaN.
        latency = self.bot.latency
        m["latency"] = 0 if latency is None or math.isnan(latency) else round(latency * 1000)

        # Database round-trip check
        m["db_online"] = False
        try:
            await self.bot.database.fetchone("SELECT 1")
            m["db_online"] = True
        except Exception as e:
            print(f"[Mod Panel] Database health check failed: {e}")

        m["templates"] = 0
        try:
            if os.path.isdir("templates"):
                m["templates"] = len([f for f in os.listdir("templates") if f.endswith(".json")])
        except Exception:
            pass

        m["pending_scheduled"] = 0
        m["next_scheduled"] = None
        try:
            row = await self.bot.database.fetchone(
                "SELECT COUNT(*) AS cnt, MIN(scheduled_time) AS next_at "
                "FROM scheduled_messages WHERE status = 'pending'"
            )
            if row:
                m["pending_scheduled"] = row["cnt"] or 0
                m["next_scheduled"] = row["next_at"]
        except Exception:
            pass

        m["summarizer_runs"] = 0
        try:
            row = await self.bot.database.fetchone("SELECT COUNT(*) AS cnt FROM summarizer_runs")
            if row:
                m["summarizer_runs"] = row["cnt"] or 0
        except Exception:
            pass

        m["deployed_reports"] = 0
        try:
            row = await self.bot.database.fetchone("SELECT COUNT(*) AS cnt FROM member_reports")
            if row:
                m["deployed_reports"] = row["cnt"] or 0
        except Exception:
            pass

        m["onboarded"] = 0
        try:
            if guild:
                row = await self.bot.database.fetchone(
                    "SELECT COUNT(*) AS cnt FROM onboarded_members WHERE guild_id = ?", (guild.id,)
                )
                if row:
                    m["onboarded"] = row["cnt"] or 0
        except Exception:
            pass

        m["tracked_panels"] = len(await get_registered_panels(self.bot))
        m["extensions"] = len(getattr(self.bot, "extensions", {}))
        m["uptime"] = _format_uptime(getattr(self.bot, "start_time", None))
        m["members"] = guild.member_count if guild and guild.member_count else 0
        return m

    async def get_panel_embed(self, guild: discord.Guild | None = None):
        m = await self._collect_metrics(guild)
        now = datetime.datetime.now(datetime.timezone.utc)
        now_ts = int(now.timestamp())

        embed = embed_builder.base_embed(
            title="True Classic • Control Panel",
            description=(
                "Select a module below to start. This panel is **persistent** — it stays live "
                "through bot restarts and code reloads.\n"
                f"◈ Last refreshed <t:{now_ts}:T> (<t:{now_ts}:R>)"
            ),
            color=embed_builder.COLOR_BRAND
        )

        db_state = "\u001b[0;32mONLINE\u001b[0m" if m["db_online"] else "\u001b[0;31mOFFLINE\u001b[0m"
        db_mark = "✓" if m["db_online"] else "✗"

        health_block = (
            "```ansi\n"
            f"{db_mark} {'Database (SQLite)':<20} {db_state}\n"
            f"✓ {'Gateway Latency':<20} \u001b[0;33m{m['latency']}ms\u001b[0m\n"
            f"✓ {'Modules Loaded':<20} \u001b[0;32m{m['extensions']} extensions\u001b[0m\n"
            f"✓ {'Uptime':<20} \u001b[0;36m{m['uptime']}\u001b[0m\n"
            f"✓ {'Embed Templates':<20} \u001b[0;36m{m['templates']} Loaded\u001b[0m\n"
            f"✓ {'Pending Schedules':<20} \u001b[0;35m{m['pending_scheduled']} Active\u001b[0m\n"
            f"✓ {'Persistent Panels':<20} \u001b[0;32m{m['tracked_panels']} Tracked\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🩺 System Health & Status", value=health_block, inline=False)

        stat_lines = [
            f"{embed_builder.ITEM_PREFIX} **Members**: {m['members']:,}" if m["members"] else None,
            f"{embed_builder.ITEM_PREFIX} **Onboarded (tracked)**: {m['onboarded']:,}",
            f"{embed_builder.ITEM_PREFIX} **Deployed Reports**: {m['deployed_reports']}",
            f"{embed_builder.ITEM_PREFIX} **Summarizer Runs**: {m['summarizer_runs']}",
        ]
        if m["next_scheduled"]:
            stat_lines.append(f"{embed_builder.ITEM_PREFIX} **Next Broadcast**: `{m['next_scheduled']}` UTC")
        embed.add_field(
            name="📊 Live Workspace Snapshot",
            value="\n".join([line for line in stat_lines if line]),
            inline=False
        )

        embed.add_field(
            name="🛠️ Available Modules & Controls",
            value=(
                "**Quick Announcement**: Rapidly post or schedule @everyone announcements across channels with banner imagery.\n"
                "**Embed Editor**: Compose multi-embed broadcasts with dynamic hydrators.\n"
                "**Member Onboarding**: Scan 30-day un-onboarded members & send deep-link DMs.\n"
                "**Member Report**: Deploy self-updating daily/weekly/monthly growth reports.\n"
                "**Scheduled Messages**: Schedule broadcasts with timezones, 5-min intervals & multi-channel targeting.\n"
                "**Summarizer**: Triage Inner Circle / Academy DM channels — who's waiting on us, what's unanswered, what to do next — "
                "plus a **Creator Care Brief** with a per-creator card for personalised customer care.\n\n"
                "🔄 **Refresh Dashboard**: Rebuilds the entire panel — re-queries every metric above and re-arms all buttons.\n"
                "🔄 **Reload Bot & Updates**: Hot-reloads all bot code, cogs, and slash commands without offline downtime."
            ),
            inline=False
        )

        embed.add_field(
            name="⭐ Prepared for True Classic",
            value="The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc.",
            inline=False
        )

        return embed

    # -- Rendering ---------------------------------------------------------

    async def show_panel(self, interaction: discord.Interaction):
        """
        Re-render the dashboard onto the panel message.

        Always builds a *fresh* view so the message ends up carrying the persistent
        panel components again (important when returning from a sub-module hub), and
        re-registers the message in the panel registry.
        """
        view = ModPanelView(self.bot)
        embed = await view.get_panel_embed(interaction.guild)
        message = interaction.message

        try:
            if interaction.response.is_done():
                if message is not None:
                    # NOTE: must be message.edit — the interaction webhook token cannot
                    # edit a message that this interaction did not create.
                    await message.edit(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.response.edit_message(embed=embed, view=view)
        except discord.HTTPException as e:
            print(f"[Mod Panel] Failed to render panel: {e}")
            try:
                await interaction.followup.send(
                    embed=embed_builder.error_embed("Panel Render Failed", f"```\n{e}\n```"),
                    ephemeral=True
                )
            except discord.HTTPException:
                pass
            return

        if message is not None and interaction.guild:
            await register_panel(self.bot, interaction.guild.id, message.channel.id, message.id)

    # -- Buttons -----------------------------------------------------------

    @discord.ui.button(label="📢 Quick Announcement", style=discord.ButtonStyle.danger, row=0, custom_id="mod_panel:quick_announcement")
    async def quick_announcement(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Quick Announcement")
        from modules.quick_announcement import QuickAnnouncementHubView
        hub_view = QuickAnnouncementHubView(self.bot, self)
        summary_embed = hub_view.build_summary_embed(interaction.guild)
        preview_embed = hub_view.state.build_announcement_embed()
        await interaction.response.edit_message(embeds=[summary_embed, preview_embed], view=hub_view)

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

    @discord.ui.button(label="🧠 Summarizer", style=discord.ButtonStyle.blurple, row=1, custom_id="mod_panel:summarizer")
    async def summarizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} selected Summarizer")
        from modules.summarizer import SummarizerHubView
        hub_view = SummarizerHubView(self.bot, self)
        embed = await hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=hub_view)

    # custom_id kept as "mod_panel:update_panel" for backwards compatibility with
    # panel messages that were posted before this button was renamed.
    @discord.ui.button(label="🔄 Refresh Dashboard", style=discord.ButtonStyle.secondary, row=1, custom_id="mod_panel:update_panel")
    async def refresh_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[Mod Panel] {interaction.user} refreshed the control panel")
        # Defer as a message update so metric queries can't hit the 3s response window.
        await interaction.response.defer()
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
