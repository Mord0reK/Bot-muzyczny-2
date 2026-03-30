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
class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Optymalizacja: Synchronizacja komend tutaj zamiast w on_ready
        # Zapobiega blokowaniu ("Rate limit") przy drobnych reconnectach
        await self.tree.sync()

bot = MusicBot()

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
    'options': '-vn -sn -dn -bufsize 5000000',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 10000000"
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
            # Wymuszenie twardego limitu czasu i użycie szybszego wezwania reconnectu
            await channel.connect(timeout=10.0, reconnect=True)
        except Exception as e:
            await ctx.send(f"Nie udało się połączyć na kanał (Błąd bramki {e}): Spróbuj jeszcze raz.")
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

class RadioSelect(discord.ui.Select):
    def __init__(self, stations):
        options = []
        for name in list(stations.keys())[:25]: # Limit do 25 opcji wg obostrzeń Discorda
            options.append(discord.SelectOption(label=name, description="Odtwórz tę stację"))
        super().__init__(placeholder="Wybierz stację radiową z listy...", min_values=1, max_values=1, options=options)
        self.stations = stations

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        station_name = self.values[0]
        station_url = self.stations[station_name]
        
        if not interaction.user.voice:
            await interaction.followup.send("Musisz najpierw dołączyć do kanału głosowego!")
            return

        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            try:
                voice_client = await channel.connect(timeout=10.0, reconnect=True)
            except Exception as e:
                await interaction.followup.send(f"Nie udało się połączyć na kanał (Błąd bramki {e}): Spróbuj jeszcze raz.")
                return
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        if voice_client.is_playing():
            voice_client.stop()

        try:
            # Rozbudowane opcje FFmpeg pod stabilność streamów z radia
            radio_ffmpeg_options = {
                'options': '-vn -sn -dn -bufsize 5000000',
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 10000000'
            }
            source = discord.FFmpegPCMAudio(station_url, **radio_ffmpeg_options)
            voice_client.play(source, after=lambda e: print(f'Zatrzymano radio: {e}') if e else None)
            await interaction.followup.send(f'📻 Opracowuję i odtwarzam radio: **{station_name}**')
        except Exception as e:
            await interaction.followup.send(f'Wystąpił twardy błąd odtwarzania streamu: {e}')

class RadioView(discord.ui.View):
    def __init__(self, stations):
        super().__init__(timeout=None)
        self.add_item(RadioSelect(stations))

@bot.hybrid_command(name='stacje', description='(Alias do /radio) Otwiera menu wyboru stacji radiowej')
async def stacje(ctx):
    await radio(ctx)

@bot.hybrid_command(name='radio', description='Otwiera wygodne menu wyboru stacji radiowej')
async def radio(ctx):
    stations = load_stations()
    view = RadioView(stations)
    await ctx.send("Wybierz interaktywną stację poniżej:", view=view)

@bot.hybrid_command(name='stop', description='Zatrzymuje bota i rozłącza z kanału')
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Rozłączono! Do zobaczenia.")
    else:
        await ctx.send("Bot nie jest na żadnym kanale.", ephemeral=True)

bot.run(TOKEN)