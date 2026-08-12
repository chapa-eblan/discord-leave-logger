"""
Discord Leave Logger Bot
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

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
    "banned_members_set": [],
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
    context = {"time": time_str, "reason": kwargs.get("reason") or "Не указана"}
    context.update(kwargs)
    try:
        return template.format(**context)
    except KeyError as e:
        print(f"⚠️ Missing variable in template: {e}", flush=True)
        return template


class ChannelSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.result = None
        self.select = discord.ui.Select(
            placeholder="Выбери текстовый канал...",
            min_values=1,
            max_values=1,
            options=[{"label": ch.name, "value": str(ch.id)} for ch in guild.text_channels],
        )
        self.add_item(self.select)

    @discord.ui.select()
    async def on_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.result = int(select.values[0])
        self.stop()
        await interaction.response.edit_message(content=f"✅ Выбран канал <#{self.result}>", view=None)

    async def on_timeout(self):
        self.stop()


class TemplateInputView(discord.ui.View):
    def __init__(self, default_template: str):
        super().__init__(timeout=180)
        self.result = default_template
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
        await interaction.response.edit_message(content="✅ Шаблон сохранён", view=None)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = self.default_template
        self.stop()
        await interaction.response.edit_message(content="🔄 Отмена — старый шаблон оставлен", view=None)

    async def on_timeout(self):
        self.result = None
        self.stop()


class LeaveLoggerBot(commands.Bot):
    def __init__(self, intents: discord.Intents):
        super().__init__(intents=intents, command_prefix=None)
        self.config = load_config()
        self._banned_user_ids = set(self.config.get("banned_members_set", []))

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print(f"   Serving {len(self.guilds)} server(s)", flush=True)
        await self.tree.sync()
        print("✅ Slash commands synced.", flush=True)
        self.config = load_config()
        self._banned_user_ids = set(self.config.get("banned_members_set", []))

    async def on_guild_member_remove(self, member: discord.Member):
        if member.id in self._banned_user_ids:
            return

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
            user=str(member),
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
        except Exception:
            pass

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"❌ Failed to send quit log: {e}", flush=True)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel_id = self.config.get("channels", {}).get("ban_log")
        if not channel_id:
            return

        channel = self.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        self._banned_user_ids.add(user.id)
        self.config["banned_members_set"] = list(self._banned_user_ids)
        save_config(self.config)

        template = self.config.get("templates", {}).get("ban")
        reason = "Не указана"
        try:
            entries = await guild.audit_logs(action=discord.AuditLogAction.ban, limit=5).flatten()
            for entry in entries:
                if entry.target.id == user.id:
                    reason = entry.reason or "Не указана"
                    break
        except Exception as e:
            print(f"⚠️ Failed to get ban reason: {e}", flush=True)

        rendered = render_template(
            template,
            user=str(user),
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
        except Exception:
            pass

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"❌ Failed to send ban log: {e}", flush=True)


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: укажи токен в переменной DISCORD_BOT_TOKEN", flush=True)
        sys.exit(1)

    intents = discord.Intents.default()
    intents.members = True
    intents.bans = True

    bot = LeaveLoggerBot(intents=intents)

    @bot.tree.command(name="setup", description="Настроить каналы и сообщения бота")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Команда доступна только на сервере.", ephemeral=True)
            return

        quit_view = ChannelSelectView(guild)
        await interaction.followup.send(
            "📋 Выбери канал для логов **ухода участников**:",
            view=quit_view,
            ephemeral=True,
        )
        quit_result = await quit_view.wait()
        if not quit_result:
            await interaction.followup.send("⏰ Время вышло. Запусти `/setup` снова.", ephemeral=True)
            return

        ban_view = ChannelSelectView(guild)
        await interaction.followup.send(
            "📋 Выбери канал для логов **банов**:",
            view=ban_view,
            ephemeral=True,
        )
        ban_result = await ban_view.wait()
        if not ban_result:
            await interaction.followup.send("⏰ Время вышло. Запусти `/setup` снова.", ephemeral=True)
            return

        cfg = load_config()
        quit_default = cfg.get("templates", {}).get("quit", "")
        quit_view_input = TemplateInputView(quit_default)
        quit_msg = "✏️ **Шаблон сообщения об уходе**\n\nПеременные: `{user}`, `{user_id}`, `{guild}`, `{time}`, `{duration}`\n\nНажми Сохранить — если всё ок."
        await interaction.followup.send(quit_msg, view=quit_view_input, ephemeral=True)
        quit_template = await quit_view_input.wait()
        if quit_template is None:
            await interaction.followup.send("⏰ Время вышло. Запусти `/setup` снова.", ephemeral=True)
            return

        ban_default = cfg.get("templates", {}).get("ban", "")
        ban_view_input = TemplateInputView(ban_default)
        ban_msg = "✏️ **Шаблон сообщения о бане**\n\nПеременные: `{user}`, `{user_id}`, `{guild}`, `{time}`, `{reason}`\n\nНажми Сохранить — если всё ок."
        await interaction.followup.send(ban_msg, view=ban_view_input, ephemeral=True)
        ban_template = await ban_view_input.wait()
        if ban_template is None:
            await interaction.followup.send("⏰ Время вышло. Запусти `/setup` снова.", ephemeral=True)
            return

        new_config = load_config()
        new_config["channels"]["quit_log"] = quit_result
        new_config["channels"]["ban_log"] = ban_result
        new_config["templates"]["quit"] = quit_template
        new_config["templates"]["ban"] = ban_template
        save_config(new_config)
        bot.config = new_config

        result_msg = f"✅ **Настройки сохранены!**\n\n📋 Канал логов ухода: <#{quit_result}>\n📋 Канал логов банов: <#{ban_result}>\n✏️ Шаблон ухода: `{quit_template}`\n✏️ Шаблон бана: `{ban_template}`"
        await interaction.followup.send(result_msg, ephemeral=True)

    @bot.tree.command(name="config", description="Посмотреть текущие настройки")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        cfg = load_config()
        channels = cfg.get("channels", {})
        templates = cfg.get("templates", {})

        quit_ch = f"<#{channels['quit_log']}>" if channels.get("quit_log") else "Не настроен"
        ban_ch = f"<#{channels['ban_log']}>" if channels.get("ban_log") else "Не настроен"
        quit_tmpl = templates.get("quit", "default")
        ban_tmpl = templates.get("ban", "default")

        msg = f"⚙️ **Настройки бота LeaveLogger**\n\n📋 **Канал логов ухода:** {quit_ch}\n📋 **Канал логов банов:** {ban_ch}\n\n**Шаблон ухода:**\n```\n{quit_tmpl}```\n\n**Шаблон бана:**\n```\n{ban_tmpl}```\n\nИспользуй `/setup` чтобы изменить настройки."
        await interaction.followup.send(msg, ephemeral=True)

    @bot.tree.command(name="ping", description="Проверить работу бота")
    async def ping_cmd(interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong!", ephemeral=True)

    print("🤖 Starting LeaveLogger Bot...", flush=True)
    bot.run(token)


if __name__ == "__main__":
    main()
