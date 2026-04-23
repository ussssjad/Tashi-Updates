"""
Discord Task Submission Bot
============================
Team leads send reminders manually via !task.
Members can accept or reject. Accepted opens a submission session valid until 11:59 PM same day.
Submissions go to the assigned team lead for approval/rejection.
Files are posted to the member's designated update thread.

Deploy on: Railway / Render / any VPS (NOT Vercel)
"""

import discord
import os
from discord.ext import commands
from discord import ui
import asyncio
import logging
from datetime import datetime
import pytz

# ═══════════════════════════════════════════════════════════════════════════════
#                            C O N F I G U R A T I O N
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TIMEZONE = pytz.timezone("Asia/Karachi")

TEAM_LEADS = {
    "tashi": {"display_name": "tashitechnologies", "user_id": 1434957366578643074},
    "asjad":  {"display_name": "ussjad",           "user_id": 1463220939151114460},
    "sarah":  {"display_name": "delta",            "user_id": 1301504724062699600},
}

MEMBER_CONFIG = {

    # ── Tashi's members ────────────────────────────────────────────────────────
    1463220939151114460: {
        "name": "Asjad",
        "team_lead": "tashi",
        "update_thread_id": 1468370899085299891,
    },
    1301504724062699600: {
        "name": "Sarah",
        "team_lead": "tashi",
        "update_thread_id": 1468370955918377042,
    },

    # ── Sarah's members ────────────────────────────────────────────────────────
    1462175465652490334: {
        "name": "Hannan",
        "team_lead": "sarah",
        "update_thread_id": 1471552489546322145,
    },
    1450779717916561468: {
        "name": "ayan",
        "team_lead": "sarah",
        "update_thread_id": 1471552126756065494,
    },
    1221024470454632558: {
        "name": "aaimlik",
        "team_lead": "sarah",
        "update_thread_id": 1490637830471553034,
    },
    1478538357188460625: {
        "name": "Seroosh",
        "team_lead": "sarah",
        "update_thread_id": 1490638048269172737,
    },

    # ── Asjad's members ────────────────────────────────────────────────────────
    1298681291633328188: {
        "name": "amna",
        "team_lead": "asjad",
        "update_thread_id": 1489277801277423687,
    },
    907733451053105152: {
        "name": "kashif",
        "team_lead": "asjad",
        "update_thread_id": 1489277943602479285,
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
#  END OF CONFIG — do not edit below unless you know what you're doing
# ═══════════════════════════════════════════════════════════════════════════════

MEMBER_IDS = list(MEMBER_CONFIG.keys())


def get_member_cfg(member_id: int) -> dict:
    return MEMBER_CONFIG.get(member_id, {})

def get_lead_key_for_member(member_id: int) -> str:
    return get_member_cfg(member_id).get("team_lead", "")

def get_lead_id_for_member(member_id: int) -> int:
    key = get_lead_key_for_member(member_id)
    return TEAM_LEADS.get(key, {}).get("user_id", 0)

def get_lead_name_for_member(member_id: int) -> str:
    key = get_lead_key_for_member(member_id)
    return TEAM_LEADS.get(key, {}).get("display_name", "Unknown Lead")

def get_lead_key_by_user_id(user_id: int) -> str:
    for key, cfg in TEAM_LEADS.items():
        if cfg["user_id"] == user_id:
            return key
    return ""

def is_team_lead_id(user_id: int) -> bool:
    return any(cfg["user_id"] == user_id for cfg in TEAM_LEADS.values())

def get_my_members(lead_user_id: int) -> list[int]:
    lead_key = get_lead_key_by_user_id(lead_user_id)
    return [uid for uid, cfg in MEMBER_CONFIG.items() if cfg["team_lead"] == lead_key]


def seconds_until_midnight() -> float:
    now      = datetime.now(TIMEZONE)
    deadline = now.replace(hour=23, minute=59, second=59, microsecond=0)
    remaining = (deadline - now).total_seconds()
    return max(remaining, 0)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("TaskBot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_collectors: set[int] = set()


def is_any_team_lead():
    async def predicate(ctx: commands.Context) -> bool:
        if is_team_lead_id(ctx.author.id):
            return True
        await ctx.send("❌ You don't have permission to use this command.")
        return False
    return commands.check(predicate)


class ReminderView(ui.View):
    def __init__(self, member: discord.User):
        # Timeout is set to exactly how many seconds remain until 11:59 PM.
        # This means the buttons automatically disable at the deadline regardless
        # of when the reminder was sent (8 AM, 1 PM, 10 PM — doesn't matter).
        super().__init__(timeout=seconds_until_midnight())
        self.member = member

    @ui.button(label="✅  Yes, I'll submit", style=discord.ButtonStyle.success, custom_id="accept_task")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        # Secondary guard: re-check the deadline at the exact moment the button
        # is pressed, in case the View timeout fired but the interaction arrived
        # in the same instant.
        if seconds_until_midnight() <= 0:
            await interaction.response.send_message(
                "🚫 **Submission window closed.** Today's deadline (11:59 PM) has already passed. "
                "Please wait for tomorrow's reminder to submit your work.",
                ephemeral=True,
            )
            self.stop()
            return

        await interaction.response.send_message(
            "Great! Please send your work now — you can attach **files** or **images**. "
            "Type `done` when you've finished submitting everything.\n\n"
            "⏳ **Deadline: 11:59 PM tonight** — your submission window closes at midnight."
        )
        self.stop()
        bot.loop.create_task(collect_submission(interaction.user, interaction.channel))

    @ui.button(label="❌  Can't submit today", style=discord.ButtonStyle.danger, custom_id="reject_task")
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Noted. Your response has been recorded as **not submitted** for today. "
            "Please reach out to your team lead if you need to discuss this.",
        )
        self.stop()
        await notify_lead_of_rejection(interaction.user)

    async def on_timeout(self):
        # Called automatically by discord.py when the deadline (11:59 PM) is
        # reached. Disables all buttons on the original reminder message so
        # members can no longer interact with it after the cutoff.
        for item in self.children:
            item.disabled = True


class ReviewView(ui.View):
    def __init__(self, member: discord.User):
        super().__init__(timeout=None)
        self.member = member

    @ui.button(label="✅  Approve", style=discord.ButtonStyle.success, custom_id="approve_work")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not is_assigned_lead(interaction.user.id, self.member.id):
            await interaction.response.send_message(
                "❌ You are not the assigned team lead for this member.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ You approved **{self.member.display_name}'s** submission. They have been notified.",
            ephemeral=True,
        )
        self.stop()
        try:
            dm = await self.member.create_dm()
            await dm.send("🎉 **Great news!** Your team lead has **approved** your submission. Well done! ✅")
        except discord.Forbidden:
            log.warning("Could not DM member %s (approval notice).", self.member.id)

    @ui.button(label="❌  Reject", style=discord.ButtonStyle.danger, custom_id="reject_work")
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        if not is_assigned_lead(interaction.user.id, self.member.id):
            await interaction.response.send_message(
                "❌ You are not the assigned team lead for this member.", ephemeral=True
            )
            return
        await interaction.response.send_modal(RejectionReasonModal(self.member))
        self.stop()


def is_assigned_lead(lead_user_id: int, member_id: int) -> bool:
    return get_lead_id_for_member(member_id) == lead_user_id


class RejectionReasonModal(ui.Modal, title="Rejection Reason"):
    reason = ui.TextInput(
        label="Reason for rejection (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Explain what needs to be fixed…",
        required=False,
        max_length=500,
    )

    def __init__(self, member: discord.User):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason.value or "No specific reason provided."
        await interaction.response.send_message(
            f"❌ Submission rejected. **{self.member.display_name}** will be asked to resubmit.",
            ephemeral=True,
        )
        try:
            dm = await self.member.create_dm()
            await dm.send(
                f"⚠️ Your team lead has **rejected** your submission.\n\n"
                f"**Reason:** {reason_text}\n\n"
                f"Please revise your work and send it again. "
                f"Attach your files or type your response below, then type `done` when finished."
            )
            bot.loop.create_task(collect_submission(self.member, dm))
        except discord.Forbidden:
            log.warning("Could not DM member %s (rejection notice).", self.member.id)


async def collect_submission(member: discord.User, channel: discord.DMChannel):
    if member.id in active_collectors:
        return

    remaining = seconds_until_midnight()
    if remaining <= 0:
        await channel.send(
            "🚫 **Submission window closed.** Today's deadline (11:59 PM) has already passed. "
            "Please wait for tomorrow's reminder to submit your work."
        )
        return

    active_collectors.add(member.id)
    collected_messages = []

    def check(m: discord.Message):
        return m.author.id == member.id and m.channel.id == channel.id

    try:
        while True:
            remaining = seconds_until_midnight()
            if remaining <= 0:
                await channel.send(
                    "🚫 **Time's up!** The submission deadline (11:59 PM) has passed. "
                    "Your session has been closed. Please contact your team lead if needed."
                )
                return

            try:
                msg = await bot.wait_for("message", check=check, timeout=remaining)
            except asyncio.TimeoutError:
                await channel.send(
                    "🚫 **Submission window closed.** The deadline (11:59 PM) has passed "
                    "and your session has expired. Please contact your team lead if needed."
                )
                return

            if msg.content.strip().lower() == "done":
                if not collected_messages:
                    await channel.send(
                        "You haven't sent anything yet! Please send your work first, then type `done`."
                    )
                    continue
                break

            collected_messages.append(msg)

        await channel.send(
            "✅ **Received!** Your files have been posted to your update thread, "
            "and your submission has been forwarded to your team lead for review. "
            "You'll get a notification once they've reviewed it."
        )

        await post_files_to_update_thread(member, collected_messages)
        await forward_to_lead(member, collected_messages)

    finally:
        active_collectors.discard(member.id)


async def post_files_to_update_thread(member: discord.User, messages: list[discord.Message]):
    thread_id = get_member_cfg(member.id).get("update_thread_id", 0)
    if not thread_id:
        log.warning("No update_thread_id set for member %d — skipping file post.", member.id)
        return

    try:
        channel = await bot.fetch_channel(thread_id)
    except (discord.NotFound, discord.Forbidden) as e:
        log.error("Cannot access update thread %d for member %d: %s", thread_id, member.id, e)
        return

    all_files: list[discord.File] = []
    for msg in messages:
        for attachment in msg.attachments:
            try:
                all_files.append(await attachment.to_file())
            except Exception as e:
                log.warning("Could not download attachment '%s': %s", attachment.filename, e)

    if not all_files:
        log.info("No files in submission from %d — nothing to post to thread.", member.id)
        return

    timestamp = discord.utils.format_dt(discord.utils.utcnow(), style='F')
    await channel.send(f"📁 **Files submitted by {member.display_name}** — {timestamp}")
    for i in range(0, len(all_files), 10):
        await channel.send(files=all_files[i:i + 10])

    log.info("Posted %d file(s) from %s to update thread %d", len(all_files), member.name, thread_id)


async def forward_to_lead(member: discord.User, messages: list[discord.Message]):
    lead_id   = get_lead_id_for_member(member.id)
    lead_name = get_lead_name_for_member(member.id)

    if not lead_id:
        log.error("No team lead configured for member %d.", member.id)
        return

    try:
        lead    = await bot.fetch_user(lead_id)
        lead_dm = await lead.create_dm()
    except (discord.NotFound, discord.Forbidden) as e:
        log.error("Cannot reach team lead %s (%d): %s", lead_name, lead_id, e)
        return

    thread_id      = get_member_cfg(member.id).get("update_thread_id", 0)
    thread_mention = f"<#{thread_id}>" if thread_id else "_(no thread configured)_"

    await lead_dm.send(
        f"📬 **New task submission** from **{member.display_name}** (`{member.name}`)\n"
        f"Submitted at: {discord.utils.format_dt(discord.utils.utcnow(), style='F')}\n"
        f"📂 Files posted to: {thread_mention}\n"
        f"{'─' * 40}"
    )

    has_text = False
    for msg in messages:
        text       = msg.content.strip()
        file_count = len(msg.attachments)
        if text:
            has_text = True
            note = f"  _(+ {file_count} file(s) sent to thread)_" if file_count else ""
            await lead_dm.send(f"> {text}{note}")
        elif file_count:
            await lead_dm.send(f"📎 _{file_count} file(s) from this message posted to {thread_mention}_")

    if not has_text:
        await lead_dm.send("_(No text content — files only)_")

    await lead_dm.send(
        "**Please review the submission and take an action:**",
        view=ReviewView(member),
    )
    log.info("Submission from %s forwarded to lead %s (%d) only", member.name, lead_name, lead_id)


async def notify_lead_of_rejection(member: discord.User):
    lead_id   = get_lead_id_for_member(member.id)
    lead_name = get_lead_name_for_member(member.id)

    if not lead_id:
        log.error("No team lead configured for member %d.", member.id)
        return

    try:
        lead    = await bot.fetch_user(lead_id)
        lead_dm = await lead.create_dm()
        await lead_dm.send(
            f"⚠️ **{member.display_name}** (`{member.name}`) has indicated they **cannot submit** "
            f"their task today ({discord.utils.format_dt(discord.utils.utcnow(), style='D')})."
        )
        log.info("Rejection notice sent to lead %s (%d) for member %s", lead_name, lead_id, member.name)
    except (discord.NotFound, discord.Forbidden) as e:
        log.error("Cannot reach team lead %s for rejection notice: %s", lead_name, e)


async def do_send_reminders(lead_user_id: int):
    """
    Sends reminders to all members assigned to the given team lead.
    Called only via !task — no automatic scheduling.
    """
    target_ids = get_my_members(lead_user_id)
    lead_key   = get_lead_key_by_user_id(lead_user_id)
    lead_name  = TEAM_LEADS.get(lead_key, {}).get("display_name", "unknown")
    count      = len(target_ids)
    noun       = "member" if count == 1 else "members"
    log.info("Reminder triggered by lead %s — sending to their %d %s…", lead_name, count, noun)

    today = datetime.now(TIMEZONE).strftime("%A, %B %d")

    for uid in target_ids:
        try:
            user = await bot.fetch_user(uid)
            dm   = await user.create_dm()
            await dm.send(
                f"👋 Hey **{user.display_name}**!\n\n"
                f"This is your task reminder for **{today}**.\n"
                f"Please submit your work before **11:59 PM** tonight. What would you like to do?",
                view=ReminderView(user),
            )
            log.info("Reminder sent to %s (%d) — lead: %s", user.name, uid, lead_name)
        except discord.NotFound:
            log.warning("User %d not found, skipping.", uid)
        except discord.Forbidden:
            log.warning("Cannot DM user %d (DMs may be disabled).", uid)
        except Exception as e:
            log.error("Failed to send reminder to %d: %s", uid, e)

        await asyncio.sleep(1)


@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Bot ready — reminders are manual only via !task")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if (
        isinstance(message.channel, discord.DMChannel)
        and message.author.id in MEMBER_IDS
        and message.author.id not in active_collectors
        and not message.content.startswith("!")
    ):
        await message.channel.send(
            "👋 It looks like you're trying to submit something! "
            "Please wait for your 11 PM reminder, or ask your team lead to trigger one manually.\n"
            "📌 Note: submissions are only accepted until **11:59 PM** each day."
        )


@bot.command(name="task")
@is_any_team_lead()
async def task_reminder(ctx: commands.Context):
    """
    Sends a reminder to all members assigned to the lead who runs this command.
    Submissions will be valid until 11:59 PM tonight.
    """
    my_members = get_my_members(ctx.author.id)
    if not my_members:
        await ctx.send("⚠️ No members are assigned to you.")
        return
    count = len(my_members)
    noun  = "member" if count == 1 else "members"
    await ctx.send(
        f"✅ Sending reminders to your {count} {noun}…\n"
        f"📌 Their submission window is open until **11:59 PM** tonight."
    )
    await do_send_reminders(lead_user_id=ctx.author.id)


@bot.command(name="status")
@is_any_team_lead()
async def status(ctx: commands.Context):
    """
    Shows bot status — scoped to only the lead who ran this command.
    Each lead sees only their own members, not others'.
    """
    my_members = get_my_members(ctx.author.id)
    count      = len(my_members)
    noun       = "member" if count == 1 else "members"

    member_lines = "\n".join(
        f"  • {MEMBER_CONFIG[uid]['name']} (ID: `{uid}`)"
        for uid in my_members
    ) or "  _(none assigned)_"

    now       = datetime.now(TIMEZONE)
    remaining = seconds_until_midnight()
    mins_left = int(remaining // 60)

    await ctx.send(
        f"✅ **Bot is online.**\n"
        f"**Your {noun} ({count}):**\n{member_lines}\n"
        f"**Active submission sessions:** {len(active_collectors)}\n"
        f"**Current time (Karachi):** {now.strftime('%I:%M %p')}\n"
        f"**Submission window:** {'Open — ' + str(mins_left) + ' min remaining today' if remaining > 0 else '🔴 Closed (past 11:59 PM)'}\n"
        f"ℹ️ Reminders are sent manually via `!task`."
    )


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
