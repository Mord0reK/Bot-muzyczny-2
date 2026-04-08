import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import time
import aiohttp

from config.toml_config import load_config, format_config, set_value, get_editable_keys, get_key_descriptions

# YT-DLP / FFmpeg setup
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
    'source_address': '0.0.0.0', 
}

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

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

class GeneralCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- KOMENDY MUZYCZNE ---
    
    @commands.hybrid_command(name="play", description="Odtwarza muzykę z YouTube.")
    async def play(self, ctx: commands.Context, *, link_lub_nazwa: str):
        # Aby zapobiec błędowi "Aplikacja nie reaguje", odraczamy odpowiedź (bot ma wtedy do 15 min na przetworzenie)
        await ctx.defer()

        if getattr(ctx.author, "voice", None) is None:
            await ctx.send("Musisz być na kanale głosowym na serwerze!")
            return

        channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        vc = ctx.voice_client
        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(link_lub_nazwa, loop=self.bot.loop, stream=True)
                vc.play(player)
                await ctx.send(f'Teraz gram: **{player.title}**')
            except Exception as e:
                await ctx.send(f"Wystąpił błąd podczas odtwarzania: {e}")

    @commands.hybrid_command(name="pause", description="Pauzuje muzykę.")
    async def pause(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Zapauzowano.")
        else:
            await ctx.send("Nic teraz nie gram.")

    @commands.hybrid_command(name="resume", description="Wznawia muzykę.")
    async def resume(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Wznowiono.")
        else:
            await ctx.send("Muzyka nie jest zapauzowana.")

    @commands.hybrid_command(name="skip", description="Pomija aktualny utwór.")
    async def skip(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Pominięto.")
        else:
            await ctx.send("Nic teraz nie gram.")

    @commands.hybrid_command(name="stop", description="Zatrzymuje muzykę i czyści odtwarzacz.")
    async def stop(self, ctx: commands.Context):
        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.send("Zatrzymano odtwarzanie.")
        else:
            await ctx.send("Bot nie działa na głosie.")

    @commands.hybrid_command(name="leave", description="Odłącza bota od kanału głosowego.")
    async def leave(self, ctx: commands.Context):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("Wyszedłem z kanału.")
        else:
            await ctx.send("Bot nie jest na kanale.")

    @commands.hybrid_command(name="radio", description="Odtwarza wybraną stację radiową.")
    @app_commands.choices(stacja=[
        app_commands.Choice(name="RMF FM", value="http://217.74.72.11/rmf_fm"),
        app_commands.Choice(name="Radio ZET", value="http://n-14-5.dcs.redcdn.pl/sc/o2/Eurozet/live/audio.livx"),
        app_commands.Choice(name="Eska", value="https://radio.streemlion.com:1500/eska"),
        app_commands.Choice(name="TOK FM", value="https://pl2.mml.com.pl:8001/tokfm"),
        app_commands.Choice(name="Antyradio", value="http://n-14-5.dcs.redcdn.pl/sc/o2/Eurozet/live/antyradio.livx"),
        app_commands.Choice(name="RMF MAXX", value="http://217.74.72.11/rmf_maxxx")
    ])
    async def radio(self, ctx: commands.Context, stacja: str):
        # Aplikujemy identyczne odroczenie odpowiedzi
        await ctx.defer()

        if getattr(ctx.author, "voice", None) is None:
            await ctx.send("Musisz być na kanale głosowym na serwerze!")
            return

        channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        vc = ctx.voice_client

        if vc.is_playing():
            vc.stop()

        # Znalezienie nazwy stacji dla lepszego komunikatu
        stacje_map = {
            "http://217.74.72.11/rmf_fm": "RMF FM",
            "http://n-14-5.dcs.redcdn.pl/sc/o2/Eurozet/live/audio.livx": "Radio ZET",
            "https://radio.streemlion.com:1500/eska": "Eska",
            "https://pl2.mml.com.pl:8001/tokfm": "TOK FM",
            "http://n-14-5.dcs.redcdn.pl/sc/o2/Eurozet/live/antyradio.livx": "Antyradio",
            "http://217.74.72.11/rmf_maxxx": "RMF MAXX"
        }
        stacja_nazwa = stacje_map.get(stacja, "Stacja Radiowa")

        async with ctx.typing():
            try:
                # W przypadku streamów radiowych możemy bezpośrednio użyć FFmpegPCMAudio
                player = discord.FFmpegPCMAudio(stacja, **ffmpeg_options)
                # Ponieważ radio streams używają często samego dźwięku, potrzebujemy transformera tylko dla głośności
                volume_player = discord.PCMVolumeTransformer(player, volume=0.5)
                vc.play(volume_player)
                await ctx.send(f'🎧 Zaczynam odtwarzać radio: **{stacja_nazwa}**')
            except Exception as e:
                await ctx.send(f"Wystąpił błąd podczas odtwarzania radia: {e}")

    # --- KOMENDY NARZĘDZIOWE ---

    @commands.hybrid_command(name="test", description="Testuje bota (ping).")
    async def test(self, ctx: commands.Context):
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://google.com") as resp:
                    await resp.read()
            except Exception:
                pass
        end = time.perf_counter()
        
        ping_ms = round((end - start) * 1000)
        discord_ping = round(self.bot.latency * 1000)

        embed = discord.Embed(title="Status Bota", color=discord.Color.green())
        embed.add_field(name="Ping HTTP", value=f"{ping_ms} ms")
        embed.add_field(name="Ping Discord", value=f"{discord_ping} ms")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="testall", description="Wykonuje pełną diagnostykę i testuje wszystkie zewnętrzne usługi bota.")
    async def testall(self, ctx: commands.Context):
        await ctx.defer()
        
        embed = discord.Embed(title="⚙️ Diagnostyka Systemów Bota", color=discord.Color.blurple())
        messages = []

        # 1. API i Sieć
        discord_ping = round(self.bot.latency * 1000)
        messages.append(f"✅ **Discord API:** Połączono ({discord_ping} ms)")

        # 2. Config
        try:
            _ = load_config()
            messages.append("✅ **Konfiguracja (TOML):** Zapis i odczyt działa")
        except Exception as e:
            messages.append(f"❌ **Konfiguracja:** Błąd ({e})")

        # 3. Yt-dlp
        try:
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info("ytsearch1:test sound", download=False))
            if 'entries' in data and len(data['entries']) > 0:
                messages.append("✅ **YT-DLP (YouTube):** Wyszukiwanie działa")
            else:
                messages.append("❌ **YT-DLP:** Brak wyników wyszukiwania")
        except Exception as e:
            messages.append(f"❌ **YT-DLP:** Błąd wyszukiwania ({e})")

        # 4. Sprawdzanie FFmpeg (wymagany do odtwarzania muzyki i radia)
        import subprocess
        try:
            process = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode == 0:
                messages.append("✅ **FFmpeg (Audio):** Zainstalowany i gotowy do strumieniania")
            else:
                messages.append("❌ **FFmpeg:** Zainstalowany nieprawidłowo")
        except FileNotFoundError:
            messages.append("❌ **FFmpeg:** Nie znaleziono! Muzyka (play/radio) nie będzie działać.")

        # 5. Głos i uprawnienia
        if getattr(ctx.author, "voice", None) and ctx.author.voice.channel:
            perms = ctx.author.voice.channel.permissions_for(ctx.guild.me)
            if perms.connect and perms.speak:
                messages.append("✅ **Uprawnienia Kanału:** Mam dostęp do łączenia i mówienia")
            else:
                messages.append("❌ **Uprawnienia Kanału:** Brak puszczenia głosu lub mówienia (Connect/Speak)")
        else:
            messages.append("⚠️ **Uprawnienia Kanału:** (Wejdź na kanał głosowy, by to sprawdzić)")

        embed.description = "\n".join(messages)
        await ctx.send(embed=embed)


class ConfigGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="config", description="Zarządzanie konfiguracją bota")

    @app_commands.command(name="view", description="Wyświetla aktualną konfigurację bota")
    async def view(self, interaction: discord.Interaction):
        text = format_config(load_config())
        embed = discord.Embed(title="Konfiguracja bota", description=text, color=discord.Color.blue())
        embed.set_footer(text="/config set <klucz> <wartość>")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="set", description="Zmienia wartość w konfiguracji bota")
    async def set(self, interaction: discord.Interaction, key: str, value: str):
        parts = key.split(".", 1)
        if len(parts) != 2:
            return await interaction.response.send_message("Błędny format. Użyj: `sekcja.klucz`", ephemeral=True)
        
        if set_value(parts[0], parts[1], value):
            await interaction.response.send_message(f"Zaktualizowano `{key}` = `{value}`")
        else:
            await interaction.response.send_message("Błąd przy zapisie.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GeneralCommands(bot))
    bot.tree.add_command(ConfigGroup())