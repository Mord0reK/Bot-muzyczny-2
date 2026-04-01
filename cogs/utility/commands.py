import discord
from discord.ext import commands
from discord import app_commands

from config.toml_config import load_config, format_config, set_value, get_editable_keys, get_key_descriptions


class ConfigGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="config", description="Zarządzanie konfiguracją bota")

    @app_commands.command(name="view", description="Wyświetla aktualną konfigurację bota")
    async def view(self, interaction: discord.Interaction):
        cfg = load_config()
        text = format_config(cfg)
        embed = discord.Embed(
            title="Konfiguracja bota",
            description=text,
            color=discord.Color.blue(),
        )
        embed.set_footer(text="/config set <klucz> <wartość> — aby zmienić")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="set", description="Zmienia wartość w konfiguracji bota")
    @app_commands.describe(key="Klucz ustawienia (np. voice.default_volume)")
    @app_commands.describe(value="Nowa wartość")
    @app_commands.choices(key=[
        app_commands.Choice(name=f"{section}.{k}: {desc}", value=f"{section}.{k}")
        for section, keys in get_editable_keys().items()
        for k in keys
        for desc in [get_key_descriptions().get(f"{section}.{k}", "")]
    ])
    async def set(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str,
    ):
        parts = key.split(".", 1)
        if len(parts) != 2:
            await interaction.response.send_message(
                "Klucz musi być w formacie `sekcja.klucz`, np. `voice.default_volume`.",
                ephemeral=True,
            )
            return

        section, k = parts
        editable = get_editable_keys()
        if section not in editable or k not in editable[section]:
            await interaction.response.send_message(
                f"Błędny klucz. Dostępne:\n"
                + "\n".join(f"  `{s}.{kk}`" for s, ks in editable.items() for kk in ks),
                ephemeral=True,
            )
            return

        cfg = load_config()
        current = cfg[section][k]

        if isinstance(current, int):
            try:
                parsed = int(value)
            except ValueError:
                await interaction.response.send_message(
                    f"`{k}` wymaga liczby całkowitej, podano `{value}`.",
                    ephemeral=True,
                )
                return
        elif isinstance(current, float):
            try:
                parsed = float(value)
            except ValueError:
                await interaction.response.send_message(
                    f"`{k}` wymaga liczby, podano `{value}`.",
                    ephemeral=True,
                )
                return
        else:
            parsed = value

        ok = set_value(section, k, parsed)
        if not ok:
            await interaction.response.send_message(
                "Nie udało się zapisać wartości.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Konfiguracja zaktualizowana",
            description=f"`[{section}]`\n`{k}` = `{parsed}`",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Niektóre zmiany wymagają restartu bota.")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    bot.tree.add_command(ConfigGroup())
