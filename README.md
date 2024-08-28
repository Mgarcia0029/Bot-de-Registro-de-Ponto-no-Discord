
# Bot de Registro de Ponto no Discord

---

## Índice
1. [Introdução](#introdução)
2. [Instalação e Configuração](#instalação-e-configuração)
3. [Funcionamento Geral do Bot](#funcionamento-geral-do-bot)
4. [Descrição dos Componentes do Código](#descrição-dos-componentes-do-código)
    - [Importação de Módulos](#importação-de-módulos)
    - [Configuração do Ambiente e Token](#configuração-do-ambiente-e-token)
    - [Classe `DiscordHandler` para Logs](#classe-discordhandler-para-logs)
    - [Configuração de Intents e Criação do Bot](#configuração-de-intents-e-criação-do-bot)
    - [Evento `on_ready`](#evento-on_ready)
    - [Dicionário de Controle de Estado dos Usuários](#dicionário-de-controle-de-estado-dos-usuários)
    - [Comando `ponto`](#comando-ponto)
    - [Classe `PontoView`](#classe-pontoview)
        - [Método `interaction_check`](#método-interaction_check)
        - [Método `log_action`](#método-log_action)
        - [Botões e seus métodos](#botões-e-seus-métodos)
5. [Teste do Bot](#teste-do-bot)
6. [Conclusão](#conclusão)

---

## Introdução

Este bot de Discord foi desenvolvido para gerenciar o registro de ponto de usuários dentro de um servidor Discord. Ele permite que os usuários façam o registro de entrada, pausa, retorno e finalização de seus dias de trabalho através de interações com botões na interface do Discord.

## Instalação e Configuração

### Requisitos:
- Python 3.8 ou superior.
- Um servidor Discord.
- Permissões de administrador no servidor Discord.

### Passos de Instalação:

1. **Clone o repositório**:
   ```bash
   git clone https://github.com/usuario/repo-bot-ponto.git
   cd repo-bot-ponto
   ```

2. **Instale as dependências**:
   Crie um ambiente virtual e ative-o:
   ```bash
   python -m venv venv
   source venv/bin/activate  # No Windows, use `venv\Scripts\activate`
   ```

   Instale as dependências listadas no arquivo `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuração do arquivo `.env`**:
   Crie um arquivo `.env` na raiz do projeto e adicione o seguinte conteúdo:
   ```env
   DISCORD_TOKEN=seu_token_discord_aqui
   COMMAND_PREFIX=!
   LOG_LEVEL=INFO
   LOG_CHANNEL_ID=ID_do_canal_de_logs
   ```

4. **Execute o bot**:
   Inicie o bot com o seguinte comando:
   ```bash
   python bot_ponto.py
   ```

## Funcionamento Geral do Bot

O bot de Registro de Ponto funciona da seguinte maneira:

1. **Início**: Um usuário pode iniciar o painel de registro de ponto usando o comando `!ponto`.
2. **Interações**: O usuário pode interagir com o painel clicando nos botões de `Entrada`, `Pausar`, `Voltar`, e `Finalizar`.
3. **Finalização**: Após a finalização do ponto, todas as mensagens e o painel são excluídos do canal.
4. **Log**: Todas as ações realizadas pelos usuários são registradas em um canal de log específico.

## Descrição dos Componentes do Código

### Importação de Módulos

O código começa com a importação dos módulos necessários:

```python
import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import os
from discord.ui import View
from dotenv import load_dotenv
import logging
```

Esses módulos são usados para criar a lógica do bot, gerenciar banco de dados, lidar com o tempo, carregar variáveis de ambiente, e fazer log de eventos.

### Configuração do Ambiente e Token

Aqui, o arquivo `.env` é carregado e as variáveis necessárias são extraídas:

```python
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_CHANNEL_ID = 1278022615440691231  # ID do canal de logs
```

### Classe `DiscordHandler` para Logs

A classe `DiscordHandler` é usada para enviar logs diretamente para um canal específico do Discord:

```python
class DiscordHandler(logging.Handler):
    def __init__(self, bot, channel_id):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def _send_log(self, message):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(message)

    def emit(self, record):
        log_entry = self.format(record)
        self.bot.loop.create_task(self._send_log(log_entry))
```

### Configuração de Intents e Criação do Bot

Aqui, configuramos os intents do bot, que especificam quais eventos o bot será capaz de ouvir:

```python
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())
```

### Evento `on_ready`

Esse evento é chamado quando o bot está pronto e conectado ao Discord:

```python
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')

    # Configuração de logs
    bot_logger = logging.getLogger('bot')
    bot_logger.setLevel(logging.INFO)

    if LOG_CHANNEL_ID:
        discord_handler = DiscordHandler(bot, LOG_CHANNEL_ID)
        discord_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
        discord_handler.setFormatter(formatter)
        bot_logger.addHandler(discord_handler)

    bot_logger.info("Bot iniciado e pronto para uso!")
```

### Dicionário de Controle de Estado dos Usuários

O bot usa um dicionário para rastrear o estado dos usuários, como se o painel de ponto está aberto ou se o ponto foi finalizado recentemente:

```python
users = {}
```

### Comando `ponto`

Este comando é utilizado para iniciar o painel de ponto:

```python
@bot.command()
async def ponto(ctx):
    # Lógica do comando ponto...
```

### Classe `PontoView`

Esta classe gerencia a interface de interação com o usuário através de botões:

#### Método `interaction_check`

Esse método verifica se o usuário pode interagir com os botões:

```python
async def interaction_check(self, interaction: discord.Interaction) -> bool:
    # Lógica de verificação...
```

#### Método `log_action`

Esse método é responsável por enviar um log de uma ação específica para o canal de log:

```python
async def log_action(self, interaction, action):
    log_message = f"{interaction.user.name} realizou a ação '{action}' no ponto."
    bot_logger = logging.getLogger('bot')
    bot_logger.info(log_message)
```

#### Botões e seus métodos

A classe `PontoView` define quatro botões com suas respectivas ações:

- **Entrada** (`entrada_button`)
- **Pausar** (`pausar_button`)
- **Voltar** (`voltar_button`)
- **Finalizar** (`finalizar_button`)

Cada botão realiza uma ação específica e interage com o banco de dados para registrar o ponto do usuário.

## Teste do Bot

### Ambiente de Teste

- **Servidor Discord**: Use um servidor de teste no Discord para validar as funcionalidades do bot.
- **SQLite Database**: O banco de dados `bateponto.db` é utilizado para armazenar os registros de ponto. Ele será criado automaticamente na primeira execução.

### Testando as Funcionalidades

1. **Inicie o bot**: Certifique-se de que o bot está online no servidor Discord.
2. **Comando `!ponto`**: Teste o comando para abrir o painel de ponto.
3. **Interações**: Verifique se as interações de entrada, pausa, voltar e finalizar estão funcionando conforme o esperado.
4. **Logs**: Verifique o canal de log para garantir que todas as ações estão sendo registradas corretamente.

## Conclusão

Este bot oferece uma solução robusta para gerenciar o registro de ponto em servidores Discord, com suporte a logs detalhados e interações fáceis de usar. Com essa documentação, você deve ser capaz de entender e modificar o bot conforme necessário, além de configurar um ambiente de teste para garantir que todas as funcionalidades estão funcionando conforme o esperado.

---

