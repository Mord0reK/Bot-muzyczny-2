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
    await bot.tree.sync()
    # Ustawienie statusu (aktywności) na Discordzie
    activity = discord.Activity(type=discord.ActivityType.listening, name="🎶 Gotowy do grania! | /play")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f'Zalogowano jako {bot.user}!')

@bot.hybrid_command(name='play', description='Odtwarza piosenkę z YT/Spotify lub ze wskazanego linku')
async def play(ctx, *, query: str):
    await ctx.defer()
    
    if not ctx.author.voice:
        await ctx.send("Musisz najpierw dołączyć do kanału głosowego!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        try:
            await channel.connect(timeout=20.0)
        except Exception as e:
            await ctx.send(f"Nie udało się połączyć: {e}")
            return
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)
            
    try:
        # Odtworzenie lub kolejkowanie (prosta wersja bez pełnej kolejki, nadpisuje obecne audio po zakończeniu)
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        ctx.voice_client.play(player, after=lambda e: print(f'Błąd odtwarzania: {e}') if e else None)
        await ctx.send(f'▶️ Teraz gram: **{player.title}**')
    except Exception as e:
        await ctx.send(f'Wystąpił błąd podczas wyszukiwania i ładowania: {e}')

@bot.hybrid_command(name='stacje', description='Wyświetla wszystkie dostępne stacje radiowe z pliku')
async def stacje(ctx):
    stations = load_stations()
    msg = "**Wszystkie dostępne stacje radiowe:**\n"
    for idx, (name, _) in enumerate(stations.items(), 1):
        msg += f"• **{name}**\n"
    msg += "\n*Użyj komendy /radio lub !radio [nazwa_stacji] aby odtworzyć (np. !radio Open FM - Vixa).* "
    await ctx.send(msg)

@bot.hybrid_command(name='radiolist', description='Wyświetla dostępne stacje radiowe z pliku (Alias)')
async def radiolist(ctx):
    await stacje(ctx)

@bot.hybrid_command(name='radio', description='Odtwarza wybraną stację radiową')
async def radio(ctx, *, station_name: str):
    await ctx.defer()
    
    if not ctx.author.voice:
        await ctx.send("Musisz najpierw dołączyć do kanału głosowego!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        try:
            await channel.connect(timeout=20.0)
        except Exception as e:
            await ctx.send(f"Nie udało się połączyć (błąd bramki głosowej): {e}")
            return
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    stations = load_stations()
    station_url = None
    for name, url in stations.items():
        if name.lower() == station_name.lower():
            station_url = url
            break
            
    if not station_url:
        await ctx.send(f'Nie znaleziono stacji: **{station_name}**. Wpisz `/stacje` aby zobaczyć listę.')
        return

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    source = discord.FFmpegPCMAudio(station_url, **ffmpeg_options)
    ctx.voice_client.play(source, after=lambda e: print(f'Błąd odtwarzania: {e}') if e else None)
    await ctx.send(f'📻 Odtwarzam radio: **{station_name}**')

@bot.hybrid_command(name='stop', description='Zatrzymuje bota i rozłącza z kanału')
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Rozłączono! Do zobaczenia.")
    else:
        await ctx.send("Bot nie jest na żadnym kanale.", ephemeral=True)

bot.run(TOKEN)