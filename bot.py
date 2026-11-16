"""
Top Creator Reserve 1:1 Channel Bot

What it does:
- On startup, creates a private 1:1 channel for every existing (non-bot) member
  who doesn't already have one.
- Whenever someone new joins, creates their private 1:1 channel automatically.
- Each channel is visible ONLY to that member, the server owner, admins, and
  (optionally) a staff role you choose.

Setup: set these environment variables on your host (Railway/Render):
  DISCORD_TOKEN    (required) your bot token from the Discord Developer Portal
  STAFF_ROLE_NAME  (optional) e.g. "Coach" — this role can also see every 1:1 channel
  WELCOME_MESSAGE  (optional) message posted in each new channel; use {mention}
                   to tag the member, e.g. "Welcome {mention}! This is your private space 🤍"
  CATEGORY_NAME    (optional) defaults to "1:1 Channels"
  CHANNEL_PREFIX   (optional) defaults to "1on1"
"""

import asyncio
import os
import re

import discord

TOKEN = os.environ["DISCORD_TOKEN"]
STAFF_ROLE_NAME = os.environ.get("STAFF_ROLE_NAME", "").strip()
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", "").strip()
CATEGORY_NAME = os.environ.get("CATEGORY_NAME", "1:1 Channels").strip()
CHANNEL_PREFIX = os.environ.get("CHANNEL_PREFIX", "1on1").strip()

MAX_PER_CATEGORY = 50  # Discord's limit
TAG = "1on1-member-id:"  # stored in each channel's topic so we never make duplicates

intents = discord.Intents.default()
intents.members = True  # requires "Server Members Intent" turned on in the Developer Portal
client = discord.Client(intents=intents)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80] or "member"


def existing_member_ids(guild: discord.Guild) -> set[int]:
    ids = set()
    for ch in guild.text_channels:
        if ch.topic and TAG in ch.topic:
            try:
                ids.add(int(ch.topic.split(TAG)[1].split()[0]))
            except (ValueError, IndexError):
                pass
    return ids


async def get_category(guild: discord.Guild) -> discord.CategoryChannel:
    """Find a 1:1 category with room, creating '1:1 Channels 2', '3', ... as needed."""
    n = 1
    while True:
        name = CATEGORY_NAME if n == 1 else f"{CATEGORY_NAME} {n}"
        cat = discord.utils.get(guild.categories, name=name)
        if cat is None:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            return await guild.create_category(name, overwrites=overwrites)
        if len(cat.channels) < MAX_PER_CATEGORY:
            return cat
        n += 1


async def create_channel(member: discord.Member) -> None:
    guild = member.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True,
        ),
    }
    if STAFF_ROLE_NAME:
        staff = discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
            )

    category = await get_category(guild)
    channel = await guild.create_text_channel(
        name=f"{CHANNEL_PREFIX}-{slug(member.display_name)}",
        category=category,
        overwrites=overwrites,
        topic=f"Private 1:1 channel for {member.display_name}. {TAG}{member.id}",
    )
    if WELCOME_MESSAGE:
        await channel.send(WELCOME_MESSAGE.replace("{mention}", member.mention))
    print(f"[{guild.name}] Created #{channel.name} for {member} ({member.id})")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    for guild in client.guilds:
        done = existing_member_ids(guild)
        todo = [m for m in guild.members if not m.bot and m.id not in done and m != guild.owner]
        print(f"[{guild.name}] {len(todo)} member(s) need a 1:1 channel")
        for member in todo:
            try:
                await create_channel(member)
                await asyncio.sleep(1.5)  # stay well under Discord rate limits
            except discord.HTTPException as e:
                print(f"[{guild.name}] Could not create channel for {member}: {e}")
        print(f"[{guild.name}] Backfill complete")


@client.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return
    if member.id in existing_member_ids(member.guild):
        return  # rejoined and already has a channel
    try:
        await create_channel(member)
    except discord.HTTPException as e:
        print(f"[{member.guild.name}] Could not create channel for {member}: {e}")


client.run(TOKEN)
