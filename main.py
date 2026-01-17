import os
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
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
# Config
# -------------------
MODEL_NAME = "gemini-2.5-flash"  # veya istediğin model listeden seç
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

# -------------------
# Utils
# -------------------
def _extract_text_from_response(data: dict) -> str:
    """
    Robust çıkarım: candidates -> candidate.content.parts[].text
    Farklı dönüş biçimlerine tolerant çalışır.
    """
    if not isinstance(data, dict):
        return str(data)

    # Primary: candidates[].content.parts[].text
    candidates = data.get("candidates") or []
    if candidates:
        cand = candidates[0]
        content = cand.get("content") or cand.get("message") or {}
        if isinstance(content, dict):
            parts = content.get("parts") or []
            texts = []
            for p in parts:
                if isinstance(p, dict):
                    if "text" in p:
                        texts.append(p["text"])
                    # inline_data or other structure: ignore for text extraction
                elif isinstance(p, str):
                    texts.append(p)
            if texts:
                return "\n".join(texts).strip()
        # fallback: candidate.text or candidate.get('output')
        if "text" in cand:
            return cand["text"].strip()
        if "output" in cand:
            # sometimes SDKs wrap text differently
            out = cand["output"]
            if isinstance(out, str):
                return out.strip()
            if isinstance(out, dict):
                return str(out)
    # SDK-level convenience field
    if "text" in data and isinstance(data["text"], str):
        return data["text"].strip()

    # final fallback: stringify
    return str(data)

# -------------------
# Gemini query (async, single-turn)
# -------------------
async def query_gemini_single_turn(prompt: str, session: aiohttp.ClientSession, timeout: int = 30) -> str:
    """
    Tek bir contents objesi ile single-turn çağrı yapar.
    Request body formatı: {"contents":[{"parts":[{"text":"..."}]}]}
    (Resmi dokümanda örnekle uyumludur). :contentReference[oaicite:1]{index=1}
    """
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY  # header ile de sağlayabilirsiniz
    }

    try:
        async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=timeout) as resp:
            text_body = await resp.text()
            if resp.status != 200:
                return f"Gemini API Error {resp.status}: {text_body}"
            # parse json safely
            data = await resp.json()
            return _extract_text_from_response(data)
    except asyncio.TimeoutError:
        return "Gemini API Error: request timed out."
    except Exception as e:
        return f"Exception while querying Gemini: {e}"

# -------------------
# Events: manage aiohttp session lifecycle
# -------------------
@bot.event
async def on_ready():
    if not getattr(bot, "http_session", None):
        bot.http_session = aiohttp.ClientSession()
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} ({bot.user.id}) — Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.event
async def on_disconnect():
    # clean up session on disconnect
    session = getattr(bot, "http_session", None)
    if session and not session.closed:
        await session.close()

# -------------------
# Slash Commands
# -------------------
@bot.tree.command(name="ping", description="Bot pingini gösterir")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

@bot.tree.command(name="ai", description="Gemini 2.5 ile single-turn sohbet (tek istekte)")
@app_commands.describe(prompt="Sorunuzu buraya yazın")
async def ai_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    session = getattr(bot, "http_session", None)
    # safety fallback: eğer session yoksa kısa ömürlü session oluştur
    created_temp_session = False
    if session is None:
        session = aiohttp.ClientSession()
        created_temp_session = True

    try:
        ai_response = await query_gemini_single_turn(prompt, session)
        # Discord mesaj limiti kontrolü
        if len(ai_response) > 2000:
            ai_response = ai_response[:1997] + "..."
        await interaction.followup.send(ai_response)
    finally:
        if created_temp_session:
            await session.close()

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
