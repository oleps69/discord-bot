import os
import discord
import requests
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# -------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Kullanılacak model
MODEL_NAME = "gemini-2.5-flash"

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateText?key={GEMINI_API_KEY}"

def query_gemini(prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "prompt": {
            "text": prompt
        },
        "temperature": temperature,
        "candidateCount": 1
    }
    try:
        r = requests.post(API_URL, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["candidates"][0]["output_text"]
        return f"Gemini API Error {r.status_code}: {r.text}"
    except Exception as e:
        return f"Exception while querying Gemini: {e}"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.tree.command(name="ping", description="Bot pingini gösterir")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

@bot.tree.command(name="ai", description="AI yanıt al")
@app_commands.describe(prompt="Sorunuzu yazın")
async def ai_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    response = query_gemini(prompt)
    if len(response) > 2000:
        response = response[:1990] + "..."
    await interaction.followup.send(response)

@bot.tree.command(name="serverinfo", description="Sunucu bilgisi")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    info = (
        f"Sunucu: {g.name}\n"
        f"Üye: {g.member_count}\n"
        f"Kanallar: {len(g.channels)}\n"
        f"Roller: {len(g.roles)}"
    )
    await interaction.response.send_message(info)

bot.run(TOKEN)
