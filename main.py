import os
import re
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict

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
MODEL_NAME = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

# -------------------
# Filter System
# -------------------
banned_words = defaultdict(dict)  # guild_id -> {"word": level}
user_violations = defaultdict(lambda: defaultdict(int))  # guild_id -> user_id -> count

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
                elif isinstance(p, str):
                    texts.append(p)
            if texts:
                return "\n".join(texts).strip()
        if "text" in cand:
            return cand["text"].strip()
        if "output" in cand:
            out = cand["output"]
            if isinstance(out, str):
                return out.strip()
            if isinstance(out, dict):
                return str(out)
    if "text" in data and isinstance(data["text"], str):
        return data["text"].strip()

    return str(data)

def normalize(text: str, level: int) -> str:
    text = text.lower()
    if level == 1:
        text = re.sub(r'[\s\-_.]+', '', text)
    elif level == 2:
        text = re.sub(r'[^a-zçğıöşü0-9]', '', text)
        text = re.sub(r'(.)\1+', r'\1', text)
    return text

def check_word(msg: str, guild_id: int) -> tuple[bool, str, int]:
    if guild_id not in banned_words:
        return False, "", 0
    
    msg_lower = msg.lower()
    for word, level in banned_words[guild_id].items():
        normalized_msg = normalize(msg_lower, level)
        normalized_word = normalize(word, level)
        if normalized_word in normalized_msg:
            return True, word, level
    return False, "", 0

async def notify_owner(guild: discord.Guild, user: discord.Member, word: str, 
                       channel: discord.TextChannel, count: int):
    owner = guild.owner
    if owner:
        try:
            embed = discord.Embed(color=0xFF0000, timestamp=datetime.utcnow())
            embed.add_field(name="User", value=f"{user.mention}", inline=False)
            embed.add_field(name="Word", value=f"||{word}||", inline=True)
            embed.add_field(name="Count", value=f"{count}/8", inline=True)
            embed.add_field(name="Channel", value=channel.mention, inline=True)
            embed.add_field(name="Server", value=guild.name, inline=True)
            embed.set_footer(text=f"ID: {user.id}")
            await owner.send(embed=embed)
        except:
            pass

# -------------------
# Gemini query (async, single-turn)
# -------------------
async def query_gemini_single_turn(prompt: str, session: aiohttp.ClientSession, timeout: int = 30) -> str:
    """
    Tek bir contents objesi ile single-turn çağrı yapar.
    Request body formatı: {"contents":[{"parts":[{"text":"..."}]}]}
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
        "x-goog-api-key": GEMINI_API_KEY
    }

    try:
        async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=timeout) as resp:
            text_body = await resp.text()
            if resp.status != 200:
                return f"Gemini API Error {resp.status}: {text_body}"
            data = await resp.json()
            return _extract_text_from_response(data)
    except asyncio.TimeoutError:
        return "Gemini API Error: request timed out."
    except Exception as e:
        return f"Exception while querying Gemini: {e}"

# -------------------
# Events
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
    session = getattr(bot, "http_session", None)
    if session and not session.closed:
        await session.close()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    
    found, word, level = check_word(message.content, message.guild.id)
    
    if found:
        user_violations[message.guild.id][message.author.id] += 1
        count = user_violations[message.guild.id][message.author.id]
        
        try:
            await message.delete()
        except:
            pass
        
        await notify_owner(message.guild, message.author, word, message.channel, count)
        
        if count >= 8:
            try:
                await message.author.ban(reason=f"Violation #{count}")
                await message.channel.send(f"{message.author.mention} banned.", delete_after=5)
            except:
                pass
        elif count >= 4:
            try:
                await message.author.kick(reason=f"Violation #{count}")
                await message.channel.send(f"{message.author.mention} kicked.", delete_after=5)
            except:
                pass
        else:
            await message.channel.send(f"{message.author.mention} warning {count}/8", delete_after=5)
    
    await bot.process_commands(message)

# -------------------
# Slash Commands
# -------------------
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        if interaction.user.id == interaction.guild.owner_id:
            return True
        if interaction.user.guild_permissions.administrator:
            return True
        return False
    return app_commands.check(predicate)

@bot.tree.command(name="no")
@app_commands.describe(word="w", level="l")
@app_commands.choices(level=[
    app_commands.Choice(name="1", value=1),
    app_commands.Choice(name="2", value=2)
])
@is_admin()
async def no_cmd(interaction: discord.Interaction, word: str, level: int):
    banned_words[interaction.guild.id][word.lower()] = level
    await interaction.response.send_message(f"✓ ||{word}|| [{level}]", ephemeral=True)

@bot.tree.command(name="ping", description="pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

@bot.tree.command(name="ai", description="gemini 2.5)")
@app_commands.describe(prompt="ask something")
async def ai_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    session = getattr(bot, "http_session", None)
    created_temp_session = False
    if session is None:
        session = aiohttp.ClientSession()
        created_temp_session = True

    try:
        ai_response = await query_gemini_single_turn(prompt, session)
        if len(ai_response) > 2000:
            ai_response = ai_response[:1997] + "..."
        await interaction.followup.send(ai_response)
    finally:
        if created_temp_session:
            await session.close()

@bot.tree.command(name="serverinfo", description="dont use if you are not white")
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
