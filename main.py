import os
import discord
from discord.ext import commands
from discord import app_commands
import requests

# -------------------
# CONFIG
# -------------------
TOKEN = os.getenv("BOT_TOKEN")
HF_API_TOKEN = os.getenv("HF_API_KEY")

HF_MODEL = "tiiuae/falcon-40b-instruct"  # Large, high-quality, uncensored
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

# Protected roles/channels (sunucuya göre dinamik)
PROTECTED_ROLES = ["Admin", "Moderator"]
PROTECTED_CHANNELS = ["general", "announcements"]

# -------------------
# BOT SETUP
# -------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

# -------------------
# AI FUNCTION
# -------------------
def query_ai(prompt):
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 200, "return_full_text": False}}
    response = requests.post(HF_API_URL, headers=HEADERS, json=payload, timeout=60)
    if response.status_code == 200:
        data = response.json()
        return data[0]["generated_text"] if data else "AI bir şey üretemedi."
    else:
        return f"AI error: {response.status_code}"

# -------------------
# EVENTS
# -------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()  # GLOBAL SYNC
        print(f"Synced {len(synced)} global commands.")
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
# SLASH COMMANDS
# -------------------
@bot.tree.command(name="ping", description="Bot pingini gösterir")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

@bot.tree.command(name="ai", description="AI ile sohbet et")
@app_commands.describe(prompt="Sorunuzu buraya yazın")
async def ai_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    ai_response = query_ai(prompt)
    if len(ai_response) > 2000:
        ai_response = ai_response[:1990] + "..."
    await interaction.followup.send(ai_response)

@bot.tree.command(name="serverinfo", description="Sunucu hakkında bilgi al")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    await interaction.response.send_message(
        f"Sunucu: {g.name}\nÜye sayısı: {g.member_count}\nKanallar: {len(g.channels)}"
    )

# -------------------
# RUN
# -------------------
bot.run(TOKEN)
