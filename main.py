import os
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from dotenv import load_dotenv

# -------------------
# ENV LOAD
# -------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# -------------------
# Discord Bot Setup
# -------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# -------------------
# Protected Roles/Channels
# -------------------
PROTECTED_ROLES = ["Admin", "Moderator"]
PROTECTED_CHANNELS = ["general", "announcements"]

# -------------------
# Gemini 2.5 Flash API
# -------------------
MODEL_NAME = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

async def query_gemini(prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "prompt": {"text": prompt},
        "temperature": temperature,
        "candidateCount": 1
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_URL, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["candidates"][0]["output_text"]
                else:
                    text = await resp.text()
                    return f"Gemini API Error {resp.status}: {text}"
    except Exception as e:
        return f"Exception while querying Gemini: {e}"

# -------------------
# Events
# -------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.event
async def on_guild_role_delete(role):
    if role.name in PROTECTED_ROLES:
        await role.guild.create_role(name=role.name)
        print(f"Protected role recreated: {role.name} in {role.guild.name}")

@bot.event
async def on_guild_channel_delete(channel):
    if channel.name in PROTECTED_CHANNELS:
        await channel.guild.create_text_channel(name=channel.name)
        print(f"Protected channel recreated: {channel.name} in {channel.guild.name}")

# -------------------
# Slash Commands
# -------------------
@bot.tree.command(name="ping", description="Bot pingini gösterir")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

@bot.tree.command(name="ai", description="Gemini 2.5 ile sohbet et")
@app_commands.describe(prompt="Sorunuzu buraya yazın")
async def ai_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    ai_response = await query_gemini(prompt)
    if len(ai_response) > 2000:
        ai_response = ai_response[:1990] + "..."
    await interaction.followup.send(ai_response)

@bot.tree.command(name="serverinfo", description="Sunucu hakkında bilgi al")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    text = (
        f"Sunucu: {g.name}\n"
        f"Üye sayısı: {g.member_count}\n"
        f"Kanallar: {len(g.channels)}\n"
        f"Roller: {len(g.roles)}"
    )
    await interaction.response.send_message(text)

# -------------------
# Run Bot
# -------------------
bot.run(TOKEN)
