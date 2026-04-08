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

import os
import logging
import asyncio

cookies_path = os.path.join(os.getcwd(), "cookies.txt")
if os.path.exists(cookies_path):
    ytdl_format_options['cookiefile'] = cookies_path
    ytdl_format_options['legacyserver'] = True
    logging.info("Znaleziono plik cookies.txt! yt-dlp użyje go do autoryzacji.")
else:
    logging.warning("Nie znaleziono pliku cookies.txt w " + cookies_path + ". yt-dlp może mieć problemy z YouTube.")

# Automatyczna próba wejścia przez nowszych klientów mobilnych do obejścia weryfikacji formatów
ytdl_format_options['extractor_args'] = {'youtube': {'player_client': ['android', 'ios']}}

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

class MusicPlayer:
    """Klasa reprezentująca odtwarzacz muzyczny na danym serwerze z obsługą kolejkowania."""
    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.current = None
        self.volume = 0.5
        self.loop_mode = "off" # off, single, queue

        self.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Oczekiwanie na kolejny utwór maksymalnie 5 minut.
                source = await asyncio.wait_for(self.queue.get(), timeout=300)
            except asyncio.TimeoutError:
                return self.destroy(self._guild)

            self.current = source
            
            if not self._guild.voice_client:
                continue

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            
            if hasattr(source, 'title'):
                await self._channel.send(f'🎶 Teraz gram: **{source.title}**')
            
            await self.next.wait()

            if self.loop_mode != "off" and isinstance(source, YTDLSource):
                # Odtwarzanie w pętli wymaga nowej instancji strumienia.
                # Do zdobycia linku źródłowego użyjemy webpage_url.
                webpage_url = source.data.get('webpage_url')
                if webpage_url:
                    try:
                        new_source = await YTDLSource.from_url(webpage_url, loop=self.bot.loop, stream=True)
                        new_source.volume = self.volume
                        
                        if self.loop_mode == "single":
                            # Wpychamy na przód, ale asyncio.Queue nie ma .insert(0).
                            # Zróbmy to poprzez odłożenie obecnych itemów na tymczasową listę
                            items = list(self.queue._queue)
                            self.queue._queue.clear()
                            self.queue.put_nowait(new_source)
                            for item in items:
                                self.queue.put_nowait(item)
                        elif self.loop_mode == "queue":
                            # Wpychamy na koniec
                            await self.queue.put(new_source)
                    except Exception:
                        pass # Pomijamy błędy przy tworzeniu pętli

            self.current = None

    def destroy(self, guild):
        return self.bot.loop.create_task(self._cog.cleanup(guild))

class GeneralCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
        return player

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            del self.players[guild.id]
        except KeyError:
            pass

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

        player = self.get_player(ctx)

        try:
            source = await YTDLSource.from_url(link_lub_nazwa, loop=self.bot.loop, stream=True)
            source.volume = player.volume
        except Exception as e:
            return await ctx.send(f"Wystąpił błąd podczas wyszukiwania: {e}")

        await player.queue.put(source)
        await ctx.send(f'✅ Dodano do kolejki: **{source.title}**')

    @commands.hybrid_command(name="queue", description="Wyświetla aktualną kolejkę utworów.")
    async def queue(self, ctx: commands.Context):
        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send("Kolejka jest obecnie pusta.")

        upcoming = list(player.queue._queue)
        msg = f"**Teraz gram:** {player.current.title if player.current else 'Nic'}\n\n**W kolejce:**\n"
        for i, track in enumerate(upcoming[:10], start=1):
            title = getattr(track, 'title', 'Nieznany tytuł')
            msg += f"`{i}.` {title}\n"
        
        if len(upcoming) > 10:
            msg += f"\n*...i {len(upcoming) - 10} więcej*"

        embed = discord.Embed(title="Kolejka utworów", description=msg, color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="nowplaying", description="Pokazuje aktualnie odtwarzany utwór.")
    async def nowplaying(self, ctx: commands.Context):
        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send("Obecnie nic nie gram.")
            
        title = getattr(player.current, 'title', 'Nieznane')
        url = getattr(player.current, 'url', '')
        embed = discord.Embed(title="Teraz gram", description=f"**[{title}]({url})**", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="volume", description="Zmienia głośność bota (1 - 100).")
    async def volume(self, ctx: commands.Context, vol: int):
        if not ctx.voice_client:
            return await ctx.send("Bot nie jest połączony z kanałem głosowym.")
        
        if getattr(ctx.author, "voice", None) is None:
            return await ctx.send("Musisz być na kanale!")

        if not (1 <= vol <= 100):
            return await ctx.send("Podaj wartość od 1 do 100.")

        player = self.get_player(ctx)
        calculated_vol = vol / 100.0
        
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = calculated_vol
            
        player.volume = calculated_vol
        await ctx.send(f"🔊 Głośność zmieniona na **{vol}%**")

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
        player = self.get_player(ctx)
        player.queue._queue.clear()
        player.loop_mode = "off"

        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.send("⏹️ Zatrzymano odtwarzanie i wyczyszczono kolejkę.")
        else:
            await ctx.send("Bot nie działa na głosie.")

    @commands.hybrid_command(name="leave", description="Odłącza bota od kanału głosowego.")
    async def leave(self, ctx: commands.Context):
        if ctx.voice_client:
            await self.cleanup(ctx.guild)
            await ctx.send("👋 Wyszedłem z kanału.")
        else:
            await ctx.send("Bot nie jest na kanale.")

    @commands.hybrid_command(name="loop", description="Przełącza tryb powtarzania (off, single, queue).")
    @app_commands.choices(tryb=[
        app_commands.Choice(name="Wyłącz (Off)", value="off"),
        app_commands.Choice(name="Pojedynczy utwór (Single)", value="single"),
        app_commands.Choice(name="Cała kolejka (Queue)", value="queue")
    ])
    async def loop(self, ctx: commands.Context, tryb: str):
        player = self.get_player(ctx)
        dostepne = {"off": "Wyłączony", "single": "Zapętlenie utworu", "queue": "Zapętlenie kolejki"}
        if tryb not in dostepne:
            return await ctx.send("Zły tryb. Wybierz `off`, `single` lub `queue`.")

        player.loop_mode = tryb
        await ctx.send(f"🔁 Tryb powtarzania ustawiony na: **{dostepne[tryb]}**")

    @commands.hybrid_command(name="shuffle", description="Miesza obecną kolejkę utworów.")
    async def shuffle(self, ctx: commands.Context):
        import random
        player = self.get_player(ctx)
        if player.queue.qsize() < 2:
            return await ctx.send("Za mała ilość utworów do modyfikacji (potrzeba min. 2 w kolejce).")

        l = list(player.queue._queue)
        random.shuffle(l)
        player.queue._queue.clear()
        for item in l:
            player.queue.put_nowait(item)

        await ctx.send("🔀 Przetasowano kolejkę!")

    @commands.hybrid_command(name="remove", description="Usuwa wybrany utwór z danej pozycji kolejki.")
    async def remove(self, ctx: commands.Context, pozycja: int):
        player = self.get_player(ctx)
        
        if pozycja < 1 or pozycja > player.queue.qsize():
            return await ctx.send(f"Błędna pozycja. Podaj liczbę od 1 do {player.queue.qsize()}.")

        l = list(player.queue._queue)
        usuniete = l.pop(pozycja - 1)

        player.queue._queue.clear()
        for item in l:
            player.queue.put_nowait(item)
            
        await ctx.send(f"🗑️ Usunięto z kolejki: **{getattr(usuniete, 'title', 'Nieznany')}**")

    @commands.hybrid_command(name="clear", description="Czyści całą obecną kolejkę.")
    async def clear(self, ctx: commands.Context):
        player = self.get_player(ctx)
        player.queue._queue.clear()
        await ctx.send("🔥 Kolejka została wyczyszczona!")

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

        player = self.get_player(ctx)

        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        player.queue._queue.clear()

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

        try:
            # W przypadku streamów radiowych możemy bezpośrednio użyć FFmpegPCMAudio
            player_source = discord.FFmpegPCMAudio(stacja, **ffmpeg_options)
            # Ponieważ radio streams używają często samego dźwięku, potrzebujemy transformera tylko dla głośności
            volume_player = discord.PCMVolumeTransformer(player_source, volume=player.volume)
            setattr(volume_player, 'title', stacja_nazwa)
            await player.queue.put(volume_player)
            
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