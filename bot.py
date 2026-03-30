import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import json
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Opcje dla yt-dlp, dostosowane pod słaby serwer (audio only, no playlist)
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}
ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
            
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def load_stations():
    with open('stations.json', 'r', encoding='utf-8') as f:
        return json.load(f)

@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user}!')

@bot.command(name='join', help='Dołącza do kanału głosowego')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("Musisz najpierw dołączyć do kanału głosowego!")
        return
    channel = ctx.message.author.voice.channel
    if ctx.voice_client is not None:
        return await ctx.voice_client.move_to(channel)
    await channel.connect()

@bot.command(name='play', help='Odtwarza piosenkę (URL YT/Spotify lub nazwa)')
async def play(ctx, *, query):
    if ctx.voice_client is None:
        await ctx.invoke(join)
    
    inform_msg = await ctx.send(f'Szukam i ładuję: **{query}** (może to potrwać chwilę)...')
    try:
        async with ctx.typing():
            # yt-dlp automatycznie ogarnie stream z YT
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f'Błąd odtwarzania: {e}') if e else None)
        await inform_msg.edit(content=f'Teraz gram: **{player.title}**')
    except Exception as e:
        await inform_msg.edit(content=f'Wystąpił błąd podczas ładowania: {e}')

@bot.command(name='stacje', help='Wyświetla wszystkie dostępne stacje radiowe z pliku')
async def stacje(ctx):
    stations = load_stations()
    msg = "**Wszystkie dostępne stacje radiowe:**\n"
    for idx, (name, _) in enumerate(stations.items(), 1):
        msg += f"• **{name}**\n"
    msg += "\n*Użyj komendy !radio [nazwa_stacji] aby odtworzyć (np. !radio Open FM - Vixa).* "
    await ctx.send(msg)

@bot.command(name='radiolist', help='Wyświetla dostępne stacje radiowe z pliku (Alias)')
async def radiolist(ctx):
    await ctx.invoke(stacje)

@bot.command(name='radio', help='Odtwarza wybraną stację radiową')
async def radio(ctx, *, station_name):
    if ctx.voice_client is None:
        await ctx.invoke(join)

    stations = load_stations()
    # Szukamy ignorując wielkość liter
    station_url = None
    for name, url in stations.items():
        if name.lower() == station_name.lower():
            station_url = url
            break
            
    if not station_url:
        await ctx.send(f'Nie znaleziono stacji: **{station_name}**. Wpisz `!radiolist` aby zobaczyć listę.')
        return

    source = discord.FFmpegPCMAudio(station_url, **ffmpeg_options)
    ctx.voice_client.play(source, after=lambda e: print(f'Błąd odtwarzania: {e}') if e else None)
    await ctx.send(f'📻 Odtwarzam radio: **{station_name}**')

@bot.command(name='stop', help='Zatrzymuje bota i rozłącza z kanału')
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Rozłączono!")

bot.run(TOKEN)