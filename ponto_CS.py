import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import os
from discord.ui import View
from dotenv import load_dotenv
import logging
import json

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_CHANNEL_ID = 1278022615440691231  # ID do canal de logs


# Configuração do logging para enviar logs a um canal específico no Discord
class DiscordHandler(logging.Handler):
    def __init__(self, bot, channel_id):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def _send_log(self, message):
        # Enviar a mensagem de log para o canal especificado
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(message)

    def emit(self, record):
        log_entry = self.format(record)
        self.bot.loop.create_task(self._send_log(log_entry))


# Configuração dos intents do bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())


@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')

    # Configure o logger agora que o bot está pronto
    bot_logger = logging.getLogger('bot')
    bot_logger.setLevel(logging.INFO)

    if LOG_CHANNEL_ID:
        discord_handler = DiscordHandler(bot, LOG_CHANNEL_ID)
        discord_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
        discord_handler.setFormatter(formatter)
        bot_logger.addHandler(discord_handler)

    bot_logger.info("Bot iniciado e pronto para uso!")


# Dicionário para armazenar o estado dos usuários e se o painel está ativo
users = {}


@bot.command()
async def ponto(ctx):
    user_id = str(ctx.author.id)

    # Verifica se o usuário já tem um painel aberto
    if user_id in users and users[user_id].get("painel_aberto"):
        await ctx.send("Você já tem um painel aberto. Finalize-o antes de abrir um novo.")
        return

    # Verifica se o usuário já fechou o ponto e está dentro do tempo de tolerância
    if user_id in users and users[user_id].get("ultimo_fechamento"):
        tempo_restante = users[user_id]["ultimo_fechamento"] + timedelta(minutes=2) - datetime.now()
        if tempo_restante.total_seconds() > 0:
            minutos, segundos = divmod(int(tempo_restante.total_seconds()), 60)
            await ctx.send(f"Você deve esperar {minutos} minutos e {segundos} segundos para abrir um novo ponto.")
            return

    embed = discord.Embed(
        title="🔄 **Registro de Ponto**",
        description="*Selecione uma das opções abaixo para registrar seu ponto:*",
        color=0xFF5733
    )
    embed.add_field(name="🔓 **Entrada**", value="Inicie seu dia de trabalho.", inline=True)
    embed.add_field(name="⏸️ **Pausar**", value="Marque o horário de pausa.", inline=True)
    embed.add_field(name="🔄 **Voltar**", value="Registre o retorno da pausa.", inline=True)
    embed.add_field(name="🚪 **Finalizar**", value="Finalize seu dia de trabalho.", inline=True)
    embed.set_footer(text="Registro de Ponto • Seu Bot")

    view = PontoView(user_id=user_id, message=ctx.message)  # Passa o ID do usuário e a mensagem original para PontoView
    users[user_id] = {"painel_aberto": True, "view": view}  # Marca que o painel está aberto
    await ctx.send(embed=embed, view=view)


# Classe para a interação com os botões de ponto
class PontoView(View):
    def __init__(self, user_id, message):
        super().__init__()
        self.user_id = user_id
        self.message = message
        self.conn = sqlite3.connect('bateponto.db')
        self.c = self.conn.cursor()
        self.c.execute('''CREATE TABLE IF NOT EXISTS pontos (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            username TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            tipo TEXT NOT NULL)''')
        self.conn.commit()

    def verificar_ponto_aberto(self, user_id):
        """Verifica se há um ponto de entrada sem finalização."""
        self.c.execute('''
            SELECT id, user_id FROM pontos 
            WHERE user_id = ? AND tipo = "entrada"
            AND NOT EXISTS (
                SELECT 1 FROM pontos p2 
                WHERE p2.user_id = pontos.user_id 
                AND p2.tipo = "finalizar" 
                AND p2.timestamp > pontos.timestamp
            )
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (user_id,))
        return self.c.fetchone()

    def verificar_pausa_ativa(self, user_id):
        """Verifica se há uma pausa ativa que não foi finalizada."""
        self.c.execute('''
            SELECT id FROM pontos 
            WHERE user_id = ? AND tipo = "pausa"
            AND NOT EXISTS (
                SELECT 1 FROM pontos p2 
                WHERE p2.user_id = pontos.user_id 
                AND p2.tipo = "voltar" 
                AND p2.timestamp > pontos.timestamp
            )
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (user_id,))
        return self.c.fetchone()

    def registrar_ponto(self, user_id, username, tipo):
        """Registra um novo ponto no banco de dados."""
        timestamp = datetime.now().isoformat()
        self.c.execute('INSERT INTO pontos (user_id, username, timestamp, tipo) VALUES (?, ?, ?, ?)',
                       (user_id, username, timestamp, tipo))
        self.conn.commit()
        return timestamp

    def desativar_botoes(self):
        """Desativa todos os botões da interface."""
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica se a interação com os botões é permitida."""
        user_id = str(interaction.user.id)

        if user_id != self.user_id:
            await interaction.response.send_message(
                "Você não pode interagir com o ponto de outro usuário.",
                ephemeral=True
            )
            return False

        if any(item.disabled for item in self.children):
            await interaction.response.send_message(
                "Os botões estão desativados. Use `!ponto` para iniciar um novo ciclo.",
                ephemeral=True
            )
            return False
        return True

    async def log_action(self, interaction, action):
        """Envia o log de uma ação para o canal de logs."""
        log_message = f"{interaction.user.name} realizou a ação '{action}' no ponto."
        bot_logger = logging.getLogger('bot')
        bot_logger.info(log_message)

    @discord.ui.button(label="🔓 Entrada", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrada_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Ação do botão 'Entrada'."""
        user_id = str(interaction.user.id)

        ponto_aberto = self.verificar_ponto_aberto(user_id)
        if ponto_aberto:
            await interaction.response.send_message(
                f'{interaction.user.mention}, você já tem um ponto aberto. Finalize o ponto antes de abrir um novo.',
                ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "entrada")
        await interaction.response.send_message(
            f'{interaction.user.mention}, ponto de entrada registrado às {timestamp}.', ephemeral=True)
        await self.log_action(interaction, "Entrada")

    @discord.ui.button(label="⏸️ Pausar", style=discord.ButtonStyle.primary, emoji="⏸️")
    async def pausar_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Ação do botão 'Pausar'."""
        user_id = str(interaction.user.id)

        ponto_aberto = self.verificar_ponto_aberto(user_id)
        if not ponto_aberto:
            await interaction.response.send_message(
                f'{interaction.user.mention}, você precisa registrar um ponto de entrada antes de pausar.',
                ephemeral=True)
            return

        if self.verificar_pausa_ativa(user_id):
            await interaction.response.send_message(
                f'{interaction.user.mention}, você já registrou uma pausa. Utilize o botão "Voltar" para retomar o trabalho.',
                ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "pausa")
        await interaction.response.send_message(
            f'{interaction.user.mention}, ponto de pausa registrado às {timestamp}.', ephemeral=True)
        await self.log_action(interaction, "Pausar")

    @discord.ui.button(label="🔄 Voltar", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def voltar_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Ação do botão 'Voltar'."""
        user_id = str(interaction.user.id)

        if not self.verificar_pausa_ativa(user_id):
            await interaction.response.send_message(
                f'{interaction.user.mention}, você precisa registrar uma pausa antes de voltar ao trabalho.',
                ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "voltar")
        await interaction.response.send_message(
            f'{interaction.user.mention}, retorno da pausa registrado às {timestamp}.', ephemeral=True)
        await self.log_action(interaction, "Voltar")

    @discord.ui.button(label="🚪 Finalizar", style=discord.ButtonStyle.danger, emoji="🔴")
    async def finalizar_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Ação do botão 'Finalizar'."""
        user_id = str(interaction.user.id)

        # Verifica se há um ponto de entrada não finalizado
        ponto_aberto = self.verificar_ponto_aberto(user_id)
        if not ponto_aberto:
            await interaction.response.send_message(
                f'{interaction.user.mention}, você não tem nenhum ponto aberto para finalizar.', ephemeral=True)
            return

        # Registra o ponto de finalização no banco de dados
        timestamp = self.registrar_ponto(user_id, str(interaction.user), "finalizar")

        # Desativa os botões após finalização
        self.desativar_botoes()

        # Atualiza o status do usuário no dicionário 'users'
        users[user_id]["ultimo_fechamento"] = datetime.now()
        users[user_id]["painel_aberto"] = False

        # Edita a mensagem para refletir a finalização
        await interaction.response.edit_message(
            content=f'{interaction.user.mention}, ponto de finalização registrado às {timestamp}.',
            view=None  # Remove a view após finalização
        )

        # Log da ação de finalizar
        await self.log_action(interaction, "Finalizar")

        # Deleta a mensagem original para remover o painel de ponto da tela
        await self.message.delete()


# Inicializar o bot
if __name__ == "__main__":
    bot.run(TOKEN)
