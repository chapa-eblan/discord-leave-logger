"""
Discord Leave Logger Bot

Logs when members leave or get banned from the server.
Configurable via slash commands.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "channels": {
        "quit_log": None,
        "ban_log": None,
    },
    "templates": {
        "quit": "👋 `{user}` покинул сервер `{guild}` | `{time}`",
        "ban": "🔨 `{user}` забанен на `{guild}` | `{time}` | Причина: `{reason}`",
    },
    "joined_at_enabled": True,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def get_user_display(member_or_user) -> str:
    return str(member_or_user)


def format_duration(joined_at: datetime, left_at: datetime) -> str:
    delta = left_at - joined_at
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    if days == 0:
        if hours == 0:
            return f"{minutes} мин"
        return f"{hours} ч {minutes} мин"
    elif days == 1:
        return f"1 день, {hours} ч"
    return f"{days} дн, {hours} ч"


def render_template(template: str, **kwargs) -> str:
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%d.%m.%Y %H:%M")

    context = {
        "time": time_str,
        "reason": kwargs.get("reason") or "Не указана",
    }
    context.update(kwargs)

    return template.format(**context)


class ChannelSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.result: Optional[int] = None

    def populate_options(self, guild: discord.Guild):
        self.clear_items()
        select = discord.ui.Select(
            placeholder="Выбери текстовый канал...",
            min_values=1,
            max_values=1,
        )

        for ch in guild.text_channels:
            select.add_option(label=ch.name, value=str(ch.id))

        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        self.result = int(interaction.data["values"][0])
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.stop()


class TemplateInputView(discord.ui.View):
    def __init__(self, default_template: str):
        super().__init__(timeout=120)
        self.result: Optional[str] = default_template
        self.default_template = default_template

        self.text_input = discord.ui.TextInput(
            label="Шаблон сообщения",
            placeholder="Введи или оставь текущий...",
            default=default_template,
            required=True,
            style=discord.TextStyle.long,
        )
        self.add_item(self.text_input)

    @discord.ui.button(label="Сохранить", style=discord.ButtonStyle.primary)
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = self.text_input.value
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = self.default_template
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.result = None
        self.stop()


class LeaveLoggerBot(discord.Client):
    def __init__(self, intents: discord.Intents):
        super().__init__(intents=intents)
        self.config = load_config()
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced.")

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} (ID: {self.user.id})")
        print(f"   Serving {len(self.guilds)} server(s)")
        self.config = load_config()

    async def on_guild_member_remove(self, member: discord.Member):
        channel_id = self.config.get("channels", {}).get("quit_log")
        if not channel_id:
            return

        channel = self.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        template = self.config.get("templates", {}).get("quit")

        duration_str = None
        if self.config.get("joined_at_enabled") and member.joined_at:
            duration_str = format_duration(member.joined_at, datetime.now(timezone.utc))

        rendered = render_template(
            template,
            user=get_user_display(member),
            user_id=member.id,
            guild=member.guild.name,
            duration=duration_str or "Неизвестно",
        )

        embed = discord.Embed(
            title="👋 Участник покинул сервер",
            description=rendered,
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User ID", value=str(member.id), inline=True)
        if duration_str:
            embed.add_field(name="Был на сервере", value=duration_str, inline=True)

        try:
            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)
        except:
            pass

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"❌ Failed to send quit log: {e}")

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel_id = self.config.get("channels", {}).get("ban_log")
        if not channel_id:
            return

        channel = self.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        template = self.config.get("templates", {}).get("ban")

        reason = "Не указана"
        try:
            entries = await guild.audit_logs(action=discord.AuditLogAction.ban, limit=5).flatten()
            for entry in entries:
                if entry.target.id == user.id:
                    reason = entry.reason or "Не указана"
                    break
        except:
            pass

        rendered = render_template(
            template,
            user=get_user_display(user),
            user_id=user.id,
            guild=guild.name,
            reason=reason,
        )

        embed = discord.Embed(
            title="🔨 Участник забанен",
            description=rendered,
            color=0xE74C3C,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User ID", value=str(user.id), inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)

        try:
            if user.avatar:
                embed.set_thumbnail(url=user.avatar.url)
        except:
            pass

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"❌ Failed to send ban log: {e}")


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: укажи токен в переменной DISCORD_BOT_TOKEN")
        print("   Например: export DISCORD_BOT_TOKEN=твой-токен")
        sys.exit(1)
    if not token:
        print("❌ Ошибка: токен не найден")
        sys.exit(1)

    intents = discord.Intents.default()
    intents.members = True
    intents.bans = True

    bot = LeaveLoggerBot(intents=intents)

    # ===== Slash Commands =====

    @bot.tree.command(name="setup", description="Настроить каналы и сообщения бота")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Команда доступна только на сервере.", ephemeral=True)
            return

        # Step 1: Quit log channel
        quit_view = ChannelSelectView()
        quit_view.populate_options(guild)
        await interaction.followup.send(
            "Выбери канал для логов ухода участников:",
            view=quit_view,
            ephemeral=True,
        )
        quit_result = await quit_view.wait()
        if not quit_result:
            await interaction.followup.send("⏰ Время вышло.", ephemeral=True)
            return

        # Step 2: Ban log channel
        ban_view = ChannelSelectView()
        ban_view.populate_options(guild)
        await interaction.edit_original_response(
            "Выбери канал для логов банов:",
            view=ban_view,
        )
        ban_result = await ban_view.wait()
        if not ban_result:
            await interaction.followup.send("⏰ Время вышло.", ephemeral=True)
            return

        # Step 3: Quit template
        cfg = load_config()
        quit_default = cfg.get("templates", {}).get("quit", "")
        quit_view_input = TemplateInputView(quit_default)
        quit_msg = "Введи шаблон для сообщения об уходе.\n"
        quit_msg += "Переменные: `{user}`, `{user_id}`, `{guild}`, `{time}`, `{duration}`"
        await interaction.edit_original_response(quit_msg, view=quit_view_input)
        quit_template = await quit_view_input.wait()
        if quit_template is None:
            await interaction.followup.send("⏰ Время вышло.", ephemeral=True)
            return

        # Step 4: Ban template
        ban_default = cfg.get("templates", {}).get("ban", "")
        ban_view_input = TemplateInputView(ban_default)
        ban_msg = "Введи шаблон для сообщения о бане.\n"
        ban_msg += "Переменные: `{user}`, `{user_id}`, `{guild}`, `{time}`, `{reason}`"
        await interaction.edit_original_response(ban_msg, view=ban_view_input)
        ban_template = await ban_view_input.wait()
        if ban_template is None:
            await interaction.followup.send("⏰ Время вышло.", ephemeral=True)
            return

        # Save config
        new_config = load_config()
        new_config["channels"]["quit_log"] = quit_result
        new_config["channels"]["ban_log"] = ban_result
        new_config["templates"]["quit"] = quit_template
        new_config["templates"]["ban"] = ban_template
        save_config(new_config)
        bot.config = new_config

        result_msg = "✅ **Настройки сохранены!**\n\n"
        result_msg += f"Канал логов ухода: <#{quit_result}>\n"
        result_msg += f"Канал логов банов: <#{ban_result}>\n"
        result_msg += f"Шаблон ухода: `{quit_template}`\n"
        result_msg += f"Шаблон бана: `{ban_template}`"
        await interaction.edit_original_response(result_msg, view=None)

    @bot.tree.command(name="config", description="Посмотреть текущие настройки")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        cfg = load_config()
        channels = cfg.get("channels", {})
        templates = cfg.get("templates", {})

        quit_ch = f"<#{channels['quit_log']}>" if channels.get("quit_log") else "Не настроен"
        ban_ch = f"<#{channels['ban_log']}>" if channels.get("ban_log") else "Не настроен"

        msg = "⚙️ **Настройки бота LeaveLogger**\n\n"
        msg += f"**Канал логов ухода:** {quit_ch}\n"
        msg += f"**Канал логов банов:** {ban_ch}\n\n"
        msg += f"**Шаблон ухода:**\n```\n{templates.get('quit', 'default')}```\n\n"
        msg += f"**Шаблон бана:**\n```\n{templates.get('ban', 'default')}```\n\n"
        msg += "Используй `/setup` чтобы изменить настройки."
        await interaction.followup.send(msg, ephemeral=True)

    @bot.tree.command(name="ping", description="Проверить работу бота")
    async def ping_cmd(interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong!", ephemeral=True)

    print("🤖 Starting LeaveLogger Bot...")
    bot.run(token)


if __name__ == "__main__":
    main()
