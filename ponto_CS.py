import discord
from discord.ext import commands
import sqlite3
from datetime import datetime
import os
from discord.ui import Button, View
from dotenv import load_dotenv
import logging
import json

# Carregar o token e outras configurações do bot
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
command_prefix = os.getenv('COMMAND_PREFIX', '!')
log_level = os.getenv('LOG_LEVEL', 'INFO')

# Configuração básica do logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Logger para o seu bot
bot_logger = logging.getLogger('bot')
bot_logger.info("Bot está iniciando...")

if not token:
    raise ValueError("O token do bot não foi encontrado. Verifique se o arquivo .env está configurado corretamente.")

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=command_prefix, intents=intents, help_command=commands.DefaultHelpCommand())

# Funções de carregar e salvar comandos dinâmicos
def load_dynamic_commands():
    try:
        with open('commands.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"comandos": {}}

def save_dynamic_commands(commands_data):
    with open('commands.json', 'w') as f:
        json.dump(commands_data, f, indent=4)

# Função para registrar comandos dinâmicos
def register_dynamic_command(name, response):
    @bot.command(name=name)
    async def dynamic_command(ctx):
        await ctx.send(response)

# Carrega os comandos dinâmicos ao iniciar o bot
commands_data = load_dynamic_commands()
for cmd_name, response in commands_data["comandos"].items():
    register_dynamic_command(cmd_name, response)

# Comando para adicionar um novo comando dinâmico
@bot.command(name='addcommand')
@commands.has_permissions(administrator=True)
async def add_command(ctx, command_name: str, *, response: str):
    commands_data["comandos"][command_name] = response
    save_dynamic_commands(commands_data)
    register_dynamic_command(command_name, response)
    await ctx.send(f'Comando `{command_name}` adicionado com sucesso!')

# Comando para remover um comando dinâmico
@bot.command(name='removecommand')
@commands.has_permissions(administrator=True)
async def remove_command(ctx, command_name: str):
    if command_name in commands_data["comandos"]:
        del commands_data["comandos"][command_name]
        save_dynamic_commands(commands_data)
        bot.remove_command(command_name)
        await ctx.send(f'Comando `{command_name}` removido com sucesso!')
    else:
        await ctx.send(f'O comando `{command_name}` não existe.')

# Conectar ao banco de dados SQLite
conn = sqlite3.connect('bateponto.db')
c = conn.cursor()

# Criar tabela de registros de ponto se não existir
c.execute('''CREATE TABLE IF NOT EXISTS pontos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tipo TEXT NOT NULL)''')
conn.commit()

class PontoView(View):
    def __init__(self):
        super().__init__()

    def verificar_ponto_aberto(self, user_id):
        # Verifica se há um ponto de entrada sem um ponto de finalização correspondente
        c.execute('''
            SELECT id FROM pontos 
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
        return c.fetchone()

    def verificar_pausa_ativa(self, user_id):
        # Verifica se há uma pausa ativa que não foi finalizada com "voltar"
        c.execute('''
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
        return c.fetchone()

    def registrar_ponto(self, user_id, username, tipo):
        timestamp = datetime.now().isoformat()
        c.execute('INSERT INTO pontos (user_id, username, timestamp, tipo) VALUES (?, ?, ?, ?)',
                  (user_id, username, timestamp, tipo))
        conn.commit()
        return timestamp

    def desativar_botoes(self):
        # Desativar todos os botões após a finalização do ponto
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Bloqueia interações após os botões serem desativados
        if any(item.disabled for item in self.children):
            await interaction.response.send_message(
                "Os botões estão desativados. Use `!ponto` para iniciar um novo ciclo.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Entrada", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrada_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if self.verificar_ponto_aberto(user_id):
            await interaction.response.send_message(
                f'{interaction.user.mention}, você já tem um ponto aberto. Finalize o ponto antes de abrir um novo.',
                ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "entrada")
        await interaction.response.send_message(
            f'{interaction.user.mention}, ponto de entrada registrado às {timestamp}.', ephemeral=True)

    @discord.ui.button(label="Pausar", style=discord.ButtonStyle.primary, emoji="⏸️")
    async def pausar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if not self.verificar_ponto_aberto(user_id):
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

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def voltar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if not self.verificar_pausa_ativa(user_id):
            await interaction.response.send_message(
                f'{interaction.user.mention}, você precisa registrar uma pausa antes de voltar ao trabalho.',
                ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "voltar")
        await interaction.response.send_message(
            f'{interaction.user.mention}, retorno da pausa registrado às {timestamp}.', ephemeral=True)

    @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.danger, emoji="🔴")
    async def finalizar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if not self.verificar_ponto_aberto(user_id):
            await interaction.response.send_message(
                f'{interaction.user.mention}, você não tem nenhum ponto aberto para finalizar.', ephemeral=True)
            return

        timestamp = self.registrar_ponto(user_id, str(interaction.user), "finalizar")
        self.desativar_botoes()
        await interaction.response.edit_message(
            content=f'{interaction.user.mention}, ponto de finalização registrado às {timestamp}.',
            view=self  # Apenas esse argumento é necessário
        )
        # Após desativar, enviar uma nova mensagem informando que o ciclo foi finalizado
        await interaction.followup.send(
            f'{interaction.user.mention}, você finalizou o seu dia de trabalho. Use o comando `!ponto` para iniciar um novo ciclo de Trabalho.',
            ephemeral=True
        )

# Comando para enviar a mensagem com os botões
@bot.command(name='ponto')
async def ponto(ctx):
    embed = discord.Embed(title="Registro de Ponto",
                          description="**Selecione uma das opções abaixo:**",
                          color=0x1abc9c)
    embed.add_field(name="Entrada", value="Inicie seu dia de trabalho.", inline=True)
    embed.add_field(name="Pausar", value="Marque o horário de pausa.", inline=True)
    embed.add_field(name="Voltar", value="Registre o retorno da pausa.", inline=True)
    embed.add_field(name="Finalizar", value="Finalize seu dia de trabalho.", inline=True)
    embed.set_footer(text="Registro de Ponto • Seu Bot")

    view = PontoView()  # Cria uma nova instância de PontoView com botões ativos
    await ctx.send(embed=embed, view=view)

# Comando para alterar o prefixo
@bot.command(name='setprefix')
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, prefix):
    global command_prefix
    command_prefix = prefix
    bot.command_prefix = command_prefix
    # Salvar o novo prefixo no arquivo de configuração
    with open('config.json', 'r+') as f:
        config = json.load(f)
        config['command_prefix'] = prefix
        f.seek(0)
        json.dump(config, f, indent=4)
        f.truncate()
    await ctx.send(f'O prefixo foi alterado para: {prefix}')

# Rodar o bot
if __name__ == "__main__":
    bot.run(token)
