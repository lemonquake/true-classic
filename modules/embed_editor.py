"""
True Classic Bot - Embed Editor Module
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

import os
import json
import discord
from discord.ui import Button, View, Select, Modal, TextInput
from discord import TextStyle, ButtonStyle
import config

class SecuredView(View):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message("You do not have the required permissions to use this control panel.", ephemeral=True)
            return False
        return True

class EmbedState:
    def __init__(self):
        self.title = None
        self.description = None
        self.url = None
        self.color = 0x3498db  # Default blue
        self.author_name = None
        self.author_icon = None
        self.author_url = None
        self.image_url = None
        self.thumbnail_url = None
        self.footer_text = None
        self.footer_icon = None
        self.fields = []  # list of {"name": str, "value": str, "inline": bool}

    def copy(self):
        new_state = EmbedState()
        new_state.title = self.title
        new_state.description = self.description
        new_state.url = self.url
        new_state.color = self.color
        new_state.author_name = self.author_name
        new_state.author_icon = self.author_icon
        new_state.author_url = self.author_url
        new_state.image_url = self.image_url
        new_state.thumbnail_url = self.thumbnail_url
        new_state.footer_text = self.footer_text
        new_state.footer_icon = self.footer_icon
        new_state.fields = [f.copy() for f in self.fields]
        return new_state

    def to_discord_embed(self):
        # We need at least one field to render an embed in discord
        # If completely empty, return a placeholder so it doesn't crash
        is_empty = not (
            self.title or self.description or self.author_name or 
            self.image_url or self.thumbnail_url or self.footer_text or self.fields
        )
        
        embed = discord.Embed(
            title=self.title if self.title else (None if not is_empty else "New Embed"),
            description=self.description if self.description else (None if not is_empty else "Use edit buttons below to set content."),
            url=self.url or None,
            color=self.color
        )
        
        if self.author_name:
            embed.set_author(
                name=self.author_name,
                icon_url=self.author_icon or None,
                url=self.author_url or None
            )
        if self.image_url:
            embed.set_image(url=self.image_url)
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        if self.footer_text:
            embed.set_footer(
                text=self.footer_text,
                icon_url=self.footer_icon or None
            )
        for field in self.fields:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", True)
            )
        return embed

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "color": self.color,
            "author_name": self.author_name,
            "author_icon": self.author_icon,
            "author_url": self.author_url,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "footer_text": self.footer_text,
            "footer_icon": self.footer_icon,
            "fields": self.fields
        }

    def from_dict(self, d):
        self.title = d.get("title")
        self.description = d.get("description")
        self.url = d.get("url")
        self.color = d.get("color", 0x3498db)
        self.author_name = d.get("author_name")
        self.author_icon = d.get("author_icon")
        self.author_url = d.get("author_url")
        self.image_url = d.get("image_url")
        self.thumbnail_url = d.get("thumbnail_url")
        self.footer_text = d.get("footer_text")
        self.footer_icon = d.get("footer_icon")
        self.fields = d.get("fields", [])

class EditorSession:
    def __init__(self):
        self.embeds = [EmbedState()]
        self.current_index = 0
        self.global_text = None
        self.chosen_channels = []  # list of channel objects

    def get_current_embed(self):
        if not self.embeds:
            self.embeds = [EmbedState()]
        if self.current_index >= len(self.embeds):
            self.current_index = len(self.embeds) - 1
        return self.embeds[self.current_index]

# Modals for Embed Editing

class EmbedContentModal(Modal, title="Edit Embed Content"):
    embed_title = TextInput(label="Title", required=False, max_length=256)
    embed_desc = TextInput(label="Description", style=TextStyle.paragraph, required=False, max_length=4000)
    embed_url = TextInput(label="URL", required=False, max_length=1000)

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback
        self.embed_title.default = embed_state.title or ""
        self.embed_desc.default = embed_state.description or ""
        self.embed_url.default = embed_state.url or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_state.title = self.embed_title.value or None
        self.embed_state.description = self.embed_desc.value or None
        self.embed_state.url = self.embed_url.value or None
        await self.update_callback(interaction)

class EmbedAuthorModal(Modal, title="Edit Embed Author"):
    author_name = TextInput(label="Author Name", required=False, max_length=256)
    author_icon = TextInput(label="Author Icon URL", required=False, max_length=1000)
    author_url = TextInput(label="Author Link URL", required=False, max_length=1000)

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback
        self.author_name.default = embed_state.author_name or ""
        self.author_icon.default = embed_state.author_icon or ""
        self.author_url.default = embed_state.author_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_state.author_name = self.author_name.value or None
        self.embed_state.author_icon = self.author_icon.value or None
        self.embed_state.author_url = self.author_url.value or None
        await self.update_callback(interaction)

class EmbedImagesModal(Modal, title="Edit Embed Images"):
    image_url = TextInput(label="Main Image URL", required=False, max_length=1000)
    thumbnail_url = TextInput(label="Thumbnail URL", required=False, max_length=1000)

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback
        self.image_url.default = embed_state.image_url or ""
        self.thumbnail_url.default = embed_state.thumbnail_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_state.image_url = self.image_url.value or None
        self.embed_state.thumbnail_url = self.thumbnail_url.value or None
        await self.update_callback(interaction)

class EmbedColorModal(Modal, title="Edit Embed Color"):
    color_hex = TextInput(label="Color Hex (e.g. #3498db or 3498db)", required=True, max_length=10)

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback
        
        # Format current color as hex string
        hex_str = f"#{embed_state.color:06x}"
        self.color_hex.default = hex_str

    async def on_submit(self, interaction: discord.Interaction):
        val = self.color_hex.value.strip().lstrip("#")
        try:
            color_int = int(val, 16)
            self.embed_state.color = color_int
            await self.update_callback(interaction)
        except ValueError:
            await interaction.response.send_message("Invalid hex color format. Please try again.", ephemeral=True)

class EmbedFooterModal(Modal, title="Edit Embed Footer"):
    footer_text = TextInput(label="Footer Text", required=False, max_length=2048)
    footer_icon = TextInput(label="Footer Icon URL", required=False, max_length=1000)

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback
        self.footer_text.default = embed_state.footer_text or ""
        self.footer_icon.default = embed_state.footer_icon or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_state.footer_text = self.footer_text.value or None
        self.embed_state.footer_icon = self.footer_icon.value or None
        await self.update_callback(interaction)

class MessageTextModal(Modal, title="Edit Message Content"):
    msg_text = TextInput(label="Message Text (appears above embeds)", style=TextStyle.paragraph, required=False, max_length=2000)

    def __init__(self, session, update_callback):
        super().__init__()
        self.session = session
        self.update_callback = update_callback
        self.msg_text.default = session.global_text or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.session.global_text = self.msg_text.value or None
        await self.update_callback(interaction)

class SaveTemplateModal(Modal, title="Save Current Config"):
    name = TextInput(label="Template Name", required=True, max_length=100)

    def __init__(self, session, update_callback):
        super().__init__()
        self.session = session
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        name_val = self.name.value.strip()
        template_id = name_val.lower().replace(" ", "_")
        
        os.makedirs("templates", exist_ok=True)
        filepath = f"templates/{template_id}.json"
        
        data = {
            "name": name_val,
            "global_text": self.session.global_text,
            "embeds": [e.to_dict() for e in self.session.embeds]
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
            
        print(f"[Embed Editor] Template '{name_val}' saved as templates/{template_id}.json")
        await interaction.response.send_message(f"Saved template as '{name_val}' (ID: {template_id}).", ephemeral=True)
        await self.update_callback(interaction, defer=False)

class LoadTemplateModal(Modal, title="Load Template by ID"):
    template_id = TextInput(label="Template ID", required=True, max_length=100)

    def __init__(self, session, update_callback):
        super().__init__()
        self.session = session
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        tid = self.template_id.value.strip().lower().replace(" ", "_")
        filepath = f"templates/{tid}.json"
        
        if not os.path.exists(filepath):
            await interaction.response.send_message(f"Template '{tid}' not found.", ephemeral=True)
            return
            
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            self.session.global_text = data.get("global_text")
            self.session.embeds = []
            for ed in data.get("embeds", []):
                e = EmbedState()
                e.from_dict(ed)
                self.session.embeds.append(e)
            
            if not self.session.embeds:
                self.session.embeds = [EmbedState()]
                
            self.session.current_index = 0
            print(f"[Embed Editor] Template '{tid}' loaded successfully")
            await interaction.response.send_message(f"Template '{tid}' loaded.", ephemeral=True)
            await self.update_callback(interaction, defer=False)
        except Exception as err:
            await interaction.response.send_message(f"Error loading template: {str(err)}", ephemeral=True)

class AddFieldModal(Modal, title="Add Field"):
    field_name = TextInput(label="Field Name", required=True, max_length=256)
    field_value = TextInput(label="Field Value", style=TextStyle.paragraph, required=True, max_length=1024)
    field_inline = TextInput(label="Inline? (yes/no)", required=False, max_length=10, default="yes")

    def __init__(self, embed_state, update_callback):
        super().__init__()
        self.embed_state = embed_state
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        inline_val = self.field_inline.value.strip().lower() in ("yes", "y", "true", "t", "1")
        self.embed_state.fields.append({
            "name": self.field_name.value,
            "value": self.field_value.value,
            "inline": inline_val
        })
        await self.update_callback(interaction)

# Views for Fields and Navigation

class EditEmbedFieldsView(SecuredView):
    def __init__(self, session, parent_edit_view):
        super().__init__(timeout=300)
        self.session = session
        self.parent_edit_view = parent_edit_view
        self.embed_state = session.get_current_embed()
        
        # Add dynamic Remove select menu if fields exist
        if self.embed_state.fields:
            options = []
            for idx, field in enumerate(self.embed_state.fields):
                # truncate display strings if too long
                fname = field["name"][:30]
                fval = field["value"][:50]
                options.append(
                    discord.SelectOption(
                        label=f"{idx+1}. {fname}",
                        description=fval,
                        value=str(idx)
                    )
                )
            
            remove_select = Select(
                placeholder="Select a field to remove...",
                options=options,
                min_values=1,
                max_values=1
            )
            remove_select.callback = self.remove_field_callback
            self.add_item(remove_select)

    async def remove_field_callback(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        if 0 <= idx < len(self.embed_state.fields):
            removed = self.embed_state.fields.pop(idx)
            print(f"[Embed Editor] Removed field '{removed['name']}' from Embed #{self.session.current_index + 1}")
        
        # Refresh the field manager view
        new_view = EditEmbedFieldsView(self.session, self.parent_edit_view)
        await interaction.response.edit_message(
            embed=self.embed_state.to_discord_embed(),
            view=new_view
        )

    @discord.ui.button(label="Add Field", style=ButtonStyle.green, row=1)
    async def add_field_btn(self, interaction: discord.Interaction, button: Button):
        if len(self.embed_state.fields) >= 25:
            await interaction.response.send_message("Embeds cannot have more than 25 fields.", ephemeral=True)
            return
            
        modal = AddFieldModal(self.embed_state, self.field_added_callback)
        await interaction.response.send_modal(modal)

    async def field_added_callback(self, interaction: discord.Interaction):
        print(f"[Embed Editor] Added field to Embed #{self.session.current_index + 1}")
        new_view = EditEmbedFieldsView(self.session, self.parent_edit_view)
        await interaction.response.edit_message(
            embed=self.embed_state.to_discord_embed(),
            view=new_view
        )

    @discord.ui.button(label="Back to Edit Embed", style=ButtonStyle.blurple, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: Button):
        # Return to parent edit screen
        await interaction.response.edit_message(
            embed=self.embed_state.to_discord_embed(),
            view=self.parent_edit_view
        )

# Edit Embed Screen

class EditEmbedView(SecuredView):
    def __init__(self, session, hub_view):
        super().__init__(timeout=300)
        self.session = session
        self.hub_view = hub_view
        
        # Set navigation button states
        self.prev_btn.disabled = self.session.current_index == 0
        self.next_btn.disabled = self.session.current_index >= len(self.session.embeds) - 1

    async def refresh_edit_message(self, interaction: discord.Interaction):
        # Updates the current message with the updated embed state
        current_embed = self.session.get_current_embed()
        # Re-initialize navigation button states
        self.prev_btn.disabled = self.session.current_index == 0
        self.next_btn.disabled = self.session.current_index >= len(self.session.embeds) - 1
        
        await interaction.response.edit_message(
            embed=current_embed.to_discord_embed(),
            view=self
        )

    async def direct_refresh_edit_message(self, interaction: discord.Interaction, defer=True):
        # For calls originating from modals where interaction might have been acknowledged
        current_embed = self.session.get_current_embed()
        self.prev_btn.disabled = self.session.current_index == 0
        self.next_btn.disabled = self.session.current_index >= len(self.session.embeds) - 1
        
        if not interaction.is_expired():
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    embed=current_embed.to_discord_embed(),
                    view=self
                )
            else:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=current_embed.to_discord_embed(),
                    view=self
                )

    @discord.ui.button(label="Content", style=ButtonStyle.grey, row=0)
    async def edit_content(self, interaction: discord.Interaction, button: Button):
        modal = EmbedContentModal(self.session.get_current_embed(), self.direct_refresh_edit_message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Author", style=ButtonStyle.grey, row=0)
    async def edit_author(self, interaction: discord.Interaction, button: Button):
        modal = EmbedAuthorModal(self.session.get_current_embed(), self.direct_refresh_edit_message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Images", style=ButtonStyle.grey, row=0)
    async def edit_images(self, interaction: discord.Interaction, button: Button):
        modal = EmbedImagesModal(self.session.get_current_embed(), self.direct_refresh_edit_message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Color", style=ButtonStyle.grey, row=0)
    async def edit_color(self, interaction: discord.Interaction, button: Button):
        modal = EmbedColorModal(self.session.get_current_embed(), self.direct_refresh_edit_message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Fields", style=ButtonStyle.grey, row=1)
    async def edit_fields(self, interaction: discord.Interaction, button: Button):
        fields_view = EditEmbedFieldsView(self.session, self)
        await interaction.response.edit_message(
            embed=self.session.get_current_embed().to_discord_embed(),
            view=fields_view
        )

    @discord.ui.button(label="Footer", style=ButtonStyle.grey, row=1)
    async def edit_footer(self, interaction: discord.Interaction, button: Button):
        modal = EmbedFooterModal(self.session.get_current_embed(), self.direct_refresh_edit_message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Duplicate", style=ButtonStyle.green, row=2)
    async def duplicate_embed(self, interaction: discord.Interaction, button: Button):
        if len(self.session.embeds) >= 10:
            await interaction.response.send_message("You can have a maximum of 10 embeds.", ephemeral=True)
            return
        
        current = self.session.get_current_embed()
        duplicated = current.copy()
        
        # Insert after current index
        self.session.embeds.insert(self.session.current_index + 1, duplicated)
        self.session.current_index += 1
        print(f"[Embed Editor] Duplicated Embed #{self.session.current_index} to index {self.session.current_index + 1}")
        
        await self.refresh_edit_message(interaction)

    @discord.ui.button(label="Clear", style=ButtonStyle.red, row=2)
    async def clear_embed(self, interaction: discord.Interaction, button: Button):
        self.session.embeds[self.session.current_index] = EmbedState()
        print(f"[Embed Editor] Cleared Embed #{self.session.current_index + 1}")
        await self.refresh_edit_message(interaction)

    @discord.ui.button(label="Delete", style=ButtonStyle.red, row=2)
    async def delete_embed(self, interaction: discord.Interaction, button: Button):
        if len(self.session.embeds) <= 1:
            # Just clear it if it's the only one
            self.session.embeds[0] = EmbedState()
            print(f"[Embed Editor] Cleared the only Embed")
        else:
            old_idx = self.session.current_index
            self.session.embeds.pop(old_idx)
            # Adjust current index
            if self.session.current_index >= len(self.session.embeds):
                self.session.current_index = len(self.session.embeds) - 1
            print(f"[Embed Editor] Deleted Embed at index {old_idx + 1}")
            
        await self.refresh_edit_message(interaction)

    @discord.ui.button(label="◀ Prev", style=ButtonStyle.grey, row=3)
    async def prev_btn(self, interaction: discord.Interaction, button: Button):
        if self.session.current_index > 0:
            self.session.current_index -= 1
            await self.refresh_edit_message(interaction)

    @discord.ui.button(label="▶ Next", style=ButtonStyle.grey, row=3)
    async def next_btn(self, interaction: discord.Interaction, button: Button):
        if self.session.current_index < len(self.session.embeds) - 1:
            self.session.current_index += 1
            await self.refresh_edit_message(interaction)

    @discord.ui.button(label="➕ Add Embed", style=ButtonStyle.green, row=3)
    async def add_embed_btn(self, interaction: discord.Interaction, button: Button):
        if len(self.session.embeds) >= 10:
            await interaction.response.send_message("You can have a maximum of 10 embeds.", ephemeral=True)
            return
            
        self.session.embeds.append(EmbedState())
        self.session.current_index = len(self.session.embeds) - 1
        print(f"[Embed Editor] Added blank Embed #{len(self.session.embeds)}")
        await self.refresh_edit_message(interaction)

    @discord.ui.button(label="⬅ Back to Hub", style=ButtonStyle.blurple, row=3)
    async def back_to_hub(self, interaction: discord.Interaction, button: Button):
        # Regenerate the hub view to match updated session state
        new_hub_view = EmbedEditorHubView(self.session, self.hub_view.parent_panel_view)
        await interaction.response.edit_message(
            embed=new_hub_view.get_hub_embed(),
            view=new_hub_view
        )

# Embed Editor Hub Screen

class EmbedEditorHubView(SecuredView):
    def __init__(self, session, parent_panel_view):
        super().__init__(timeout=300)
        self.session = session
        self.parent_panel_view = parent_panel_view
        
        self.create_dynamic_buttons()

    def create_dynamic_buttons(self):
        # Clear existing buttons in Row 0/1 to recreate them dynamically
        # Keep non-dynamic items (defined below via decorators) which are placed on Row 2, 3, 4
        
        # Row 0 & 1: Embed Selector buttons
        for idx in range(len(self.session.embeds)):
            # Mark current index with an indicator
            label = f"E{idx+1} ✏️" if idx == self.session.current_index else f"E{idx+1}"
            style = ButtonStyle.blurple if idx == self.session.current_index else ButtonStyle.grey
            
            # Place up to 5 buttons per row
            row = 0 if idx < 5 else 1
            
            btn = Button(label=label, style=style, row=row, custom_id=f"sel_embed_{idx}")
            btn.callback = self.make_select_callback(idx)
            self.add_item(btn)

    def make_select_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            self.session.current_index = idx
            
            # Switch to Edit screen
            edit_view = EditEmbedView(self.session, self)
            current_embed = self.session.get_current_embed()
            
            await interaction.response.edit_message(
                embed=current_embed.to_discord_embed(),
                view=edit_view
            )
        return callback

    def get_hub_embed(self):
        embed = discord.Embed(
            title=f"🛠️ True Classic Embed Editor Hub — {len(self.session.embeds)} Embed(s)",
            description="Manage embeds, select text, save templates, and send messages.",
            color=0x3498db
        )
        
        # Channels
        if self.session.chosen_channels:
            channel_str = ", ".join([c.mention for c in self.session.chosen_channels])
        else:
            channel_str = "(none selected)"
            
        embed.add_field(name="Channels", value=channel_str, inline=False)
        
        # Global text
        gtext = self.session.global_text
        if gtext:
            if len(gtext) > 100:
                gtext_preview = gtext[:97] + "..."
            else:
                gtext_preview = gtext
        else:
            gtext_preview = "—"
        embed.add_field(name="Global Text", value=gtext_preview, inline=True)
        
        # Embed count summary
        embed.add_field(name="Embed Count", value=str(len(self.session.embeds)), inline=True)
        
        # List titles
        embeds_summary = []
        for idx, e in enumerate(self.session.embeds):
            title = e.title or "(blank description/title)"
            embeds_summary.append(f"Embed #{idx+1:02d}: {title}")
        embed.add_field(name="Embeds List", value="\n".join(embeds_summary), inline=False)
        
        return embed

    async def refresh_hub(self, interaction: discord.Interaction, defer=True):
        # Recreate dynamic buttons for row 0 and 1
        # First remove any buttons that start with 'sel_embed_' or 'add_embed_dyn'
        to_remove = [item for item in self.children if isinstance(item, Button) and item.custom_id and (item.custom_id.startswith("sel_embed_") or item.custom_id == "add_embed_dyn")]
        for item in to_remove:
            self.remove_item(item)
            
        self.create_dynamic_buttons()
        
        if not interaction.is_expired():
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    embed=self.get_hub_embed(),
                    view=self
                )
            else:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=self.get_hub_embed(),
                    view=self
                )

    # Row 1 or 0 Add Embed button dynamically added or decorator button
    @discord.ui.button(label="➕ Add Embed", style=ButtonStyle.green, row=1, custom_id="add_embed_static")
    async def add_embed_hub(self, interaction: discord.Interaction, button: Button):
        if len(self.session.embeds) >= 10:
            await interaction.response.send_message("You can have a maximum of 10 embeds.", ephemeral=True)
            return
            
        self.session.embeds.append(EmbedState())
        self.session.current_index = len(self.session.embeds) - 1
        print(f"[Embed Editor] Added Embed #{len(self.session.embeds)} from Hub")
        
        # Refresh hub
        # Recreate buttons
        to_remove = [item for item in self.children if isinstance(item, Button) and item.custom_id and item.custom_id.startswith("sel_embed_")]
        for item in to_remove:
            self.remove_item(item)
        self.create_dynamic_buttons()
        
        await interaction.response.edit_message(
            embed=self.get_hub_embed(),
            view=self
        )

    # Row 2 Actions
    @discord.ui.button(label="Message Text", style=ButtonStyle.grey, row=2)
    async def edit_message_text(self, interaction: discord.Interaction, button: Button):
        modal = MessageTextModal(self.session, self.refresh_hub)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Syntax Guide", style=ButtonStyle.grey, row=2)
    async def syntax_guide(self, interaction: discord.Interaction, button: Button):
        guide = (
            "**Discord Markdown Guide:**\n"
            "• *Italics*: `*text*` or `_text_`\n"
            "• **Bold**: `**text**`\n"
            "• ***Bold Italics***: `***text***`\n"
            "• __Underline__: `__text__`\n"
            "• ~~Strikethrough~~: `~~text~~`\n"
            "• Code Block: \\`\\`\\`text\\`\\`\\`\n"
            "• Inline Code: \\`text\\`\n"
            "• Mentions: `<@user_id>`, `<@&role_id>`, `<#channel_id>`\n"
            "• Custom Links: `[label](url)` (Only works inside Embed Descriptions or Fields)"
        )
        await interaction.response.send_message(guide, ephemeral=True)

    # Row 3 Actions
    @discord.ui.button(label="Templates", style=ButtonStyle.grey, row=3)
    async def list_templates(self, interaction: discord.Interaction, button: Button):
        os.makedirs("templates", exist_ok=True)
        files = [f[:-5] for f in os.listdir("templates") if f.endswith(".json")]
        if not files:
            await interaction.response.send_message("No templates saved yet.", ephemeral=True)
            return
            
        # Display template selector view
        options = [discord.SelectOption(label=name, value=name) for name in files[:25]]
        
        select_view = SecuredView(timeout=120)
        t_select = Select(placeholder="Choose a template to load...", options=options)
        
        async def load_callback(inter: discord.Interaction):
            val = t_select.values[0]
            filepath = f"templates/{val}.json"
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                self.session.global_text = data.get("global_text")
                self.session.embeds = []
                for ed in data.get("embeds", []):
                    e = EmbedState()
                    e.from_dict(ed)
                    self.session.embeds.append(e)
                
                if not self.session.embeds:
                    self.session.embeds = [EmbedState()]
                self.session.current_index = 0
                
                print(f"[Embed Editor] Template '{val}' loaded via dropdown")
                
                # Re-summon hub view
                new_hub = EmbedEditorHubView(self.session, self.parent_panel_view)
                await inter.response.edit_message(
                    embed=new_hub.get_hub_embed(),
                    view=new_hub
                )
            except Exception as e:
                await inter.response.send_message(f"Error loading template: {str(e)}", ephemeral=True)
        
        t_select.callback = load_callback
        select_view.add_item(t_select)
        
        # Add a back button to cancel
        cancel_btn = Button(label="Cancel", style=ButtonStyle.red)
        async def cancel_cb(inter: discord.Interaction):
            await inter.response.edit_message(
                embed=self.get_hub_embed(),
                view=self
            )
        cancel_btn.callback = cancel_cb
        select_view.add_item(cancel_btn)
        
        await interaction.response.edit_message(
            embed=discord.Embed(title="Select Template", description="Select one of the saved templates from the dropdown below:", color=0x3498db),
            view=select_view
        )

    @discord.ui.button(label="Save Template", style=ButtonStyle.green, row=3)
    async def save_template_btn(self, interaction: discord.Interaction, button: Button):
        modal = SaveTemplateModal(self.session, self.refresh_hub)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Load ID", style=ButtonStyle.grey, row=3)
    async def load_id_btn(self, interaction: discord.Interaction, button: Button):
        modal = LoadTemplateModal(self.session, self.refresh_hub)
        await interaction.response.send_modal(modal)

    # Row 4 Actions
    @discord.ui.button(label="Choose Channels", style=ButtonStyle.green, row=4)
    async def choose_channels_btn(self, interaction: discord.Interaction, button: Button):
        # Create a channel select view
        channel_select_view = SecuredView(timeout=180)
        
        c_select = discord.ui.ChannelSelect(
            placeholder="Select channels (up to 5)...",
            min_values=1,
            max_values=5,
            channel_types=[discord.ChannelType.text, discord.ChannelType.news]
        )
        
        async def c_callback(inter: discord.Interaction):
            # Resolve selected channels to actual text channels in the guild
            resolved_channels = []
            for c in c_select.values:
                real_c = inter.guild.get_channel(c.id)
                if not real_c:
                    try:
                        real_c = await inter.guild.fetch_channel(c.id)
                    except Exception:
                        pass
                if real_c:
                    resolved_channels.append(real_c)
            
            self.session.chosen_channels = resolved_channels
            print(f"[Embed Editor] Selected channels: {[c.name for c in self.session.chosen_channels]}")
            
            # Go back to Hub
            new_hub = EmbedEditorHubView(self.session, self.parent_panel_view)
            await inter.response.edit_message(
                embed=new_hub.get_hub_embed(),
                view=new_hub
            )
            
        c_select.callback = c_callback
        channel_select_view.add_item(c_select)
        
        # Cancel / Back
        back_btn = Button(label="Cancel", style=ButtonStyle.red)
        async def back_cb(inter: discord.Interaction):
            await inter.response.edit_message(
                embed=self.get_hub_embed(),
                view=self
            )
        back_btn.callback = back_cb
        channel_select_view.add_item(back_btn)
        
        await interaction.response.edit_message(
            embed=discord.Embed(title="Choose Channels", description="Select the text/announcement channels where this message should be sent:", color=0x3498db),
            view=channel_select_view
        )

    @discord.ui.button(label="Post Message", style=ButtonStyle.green, row=4)
    async def post_message_btn(self, interaction: discord.Interaction, button: Button):
        if not self.session.chosen_channels:
            await interaction.response.send_message("Please select at least one channel first using 'Choose Channels'.", ephemeral=True)
            return
            
        # Post the message
        # We need to construct list of discord.Embed
        discord_embeds = [e.to_discord_embed() for e in self.session.embeds]
        content_text = self.session.global_text or None
        
        success_channels = []
        failed_channels = []
        
        print(f"[Embed Editor] Posting message to {len(self.session.chosen_channels)} channels...")
        
        for channel in self.session.chosen_channels:
            try:
                await channel.send(content=content_text, embeds=discord_embeds)
                success_channels.append(channel.mention)
                print(f"[Embed Editor] Successfully posted message to #{channel.name} ({channel.id})")
            except Exception as e:
                failed_channels.append(f"{channel.mention} (Error: {str(e)})")
                print(f"[Embed Editor] Failed to post message to #{channel.name} ({channel.id}): {str(e)}")
                
        # Send confirmation
        status_lines = []
        if success_channels:
            status_lines.append(f"🟢 **Sent to:** {', '.join(success_channels)}")
        if failed_channels:
            status_lines.append(f"🔴 **Failed for:** {', '.join(failed_channels)}")
            
        status_msg = "\n".join(status_lines) if status_lines else "No channels processed."
        await interaction.response.send_message(f"**Post Status:**\n{status_msg}", ephemeral=True)

    @discord.ui.button(label="📅 Schedule", style=ButtonStyle.green, row=4)
    async def schedule_message_btn(self, interaction: discord.Interaction, button: Button):
        from modules.scheduled_messages import ScheduledMessagesHubView
        draft_payload = {
            "content": self.session.global_text,
            "embeds": [e.to_dict() for e in self.session.embeds]
        }
        hub_view = ScheduledMessagesHubView(interaction.client, self.parent_panel_view, draft_payload=draft_payload)
        embed = await hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=hub_view)

    @discord.ui.button(label="⬅ Back to Panel", style=ButtonStyle.blurple, row=4)
    async def back_to_panel(self, interaction: discord.Interaction, button: Button):
        # Re-render main control panel
        await self.parent_panel_view.show_panel(interaction)
