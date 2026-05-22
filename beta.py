import json
import asyncio
import os
import hashlib
import csv
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================================================
# CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE (SEGURO)
# =========================================================

# Token obrigatório. Se não existir, o bot avisa o erro antes de quebrar.
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("ERRO CRÍTICO: A variável de ambiente BOT_TOKEN não foi definida!")

# IDs de Admin vêm do Render separados por vírgula (Ex: 7188888143,1348107174)
raw_admins = os.getenv("ADMIN_IDS", "7188888143,1348107174")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

# Senha padrão se não for definida no Render
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "luansantana")
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

SESSION_TIME = 1800

# Se você usar Render Volumes, configure DATA_DIR para o ponto de montagem (ex: /data)
DATA_DIR = os.getenv("DATA_DIR", ".")
DB_FILE = os.path.join(DATA_DIR, "db.json")
CSV_FILE = os.path.join(DATA_DIR, "confirmados.csv")

admin_session = {}
user_state = {}

# Trava para evitar corrupção de dados no JSON em acessos simultâneos
db_lock = asyncio.Lock()

# =========================================================
# BANCO DE DADOS (JSON COM PROTEÇÃO DE CONCORRÊNCIA)
# =========================================================

DEFAULT_DB = {
    "users": [],
    "confirmacoes": {},
    "stats": {
        "confirmacoes": 0,
        "recusados": 0,
        "pendentes": 0,
        "reembolsados": 0,
        "clicks": {"betmgm": 0, "novibet": 0, "jonbet": 0}
    },
    "config": {
        "texto_start": "🔥 Bem-vindo ao sistema!",
        "menu_start": "👇 Escolha uma casa:",
        "confirm_msg1": "🔥 Fechou, {nome}! Tá na aposta",
        "confirm_msg2": "📈 Agora acompanhe o jogo",
        "confirm_msg3": "🍀 Boa sorte {nome}",
        "confirm_msg4": "📸 Envie 2 prints da aposta",
        "confirmar_botao": "✅ Já fiz a aposta",
        "delay_confirmacao": 20,
        "ativo_betmgm": True,
        "ativo_novibet": True,
        "ativo_jonbet": True,
        "nome_betmgm": "🎰 BetMGM",
        "nome_novibet": "🎰 Novibet",
        "nome_jonbet": "🎰 Jonbet",
        "betmgm": "https://google.com",
        "novibet": "https://google.com",
        "jonbet": "https://google.com",
        "texto_betmgm": "🔥 Entrada disponível na BetMGM",
        "texto_novibet": "🔥 Entrada disponível na Novibet",
        "texto_jonbet": "🔥 Entrada disponível na Jonbet"
    }
}

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erro ao ler db.json (pode estar corrompido): {e}")
            return DEFAULT_DB
    return DEFAULT_DB

db = load_db()

async def save_db_async():
    """Salva o banco de forma assíncrona protegida por Lock contra corrupção"""
    async with db_lock:
        try:
            # Roda a escrita de arquivo em um executor para não travar o loop do bot
            await asyncio.to_thread(_write_db)
        except Exception as e:
            print(f"❌ Erro grave ao salvar banco de dados: {e}")

def _write_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# =========================================================
# HELPERS
# =========================================================

async def add_user(uid):
    if uid not in db["users"]:
        db["users"].append(uid)
        await save_db_async()

def is_admin(uid):
    return uid in ADMIN_IDS

def admin_logged(uid):
    if uid not in admin_session:
        return False
    session = admin_session.get(uid)
    if not isinstance(session, dict):
        return False
    agora = time.time()
    if agora - session["time"] > SESSION_TIME:
        admin_session.pop(uid, None)
        return False
    admin_session[uid]["time"] = agora
    return True

def start_keyboard():
    keyboard = []
    casas = ["betmgm", "novibet", "jonbet"]
    for casa in casas:
        if db["config"].get(f"ativo_{casa}"):
            keyboard.append([
                InlineKeyboardButton(
                    db["config"].get(f"nome_{casa}", casa.upper()),
                    callback_data=casa
                )
            ])
    return InlineKeyboardMarkup(keyboard)

def export_csv():
    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["id", "nome", "username", "casa", "status", "data"])
            for uid, dados in db["confirmacoes"].items():
                writer.writerow([
                    uid,
                    dados.get("nome"),
                    dados.get("username"),
                    dados.get("casa"),
                    dados.get("status"),
                    dados.get("data")
                ])
    except Exception as e:
        print(f"❌ Erro ao exportar CSV: {e}")

# =========================================================
# COMANDOS PRINCIPAIS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id

    await add_user(uid)

    await context.bot.send_message(chat_id, db["config"]["texto_start"])
    await context.bot.send_message(
        chat_id,
        db["config"]["menu_start"],
        reply_markup=start_keyboard()
    )

async def fluxo(chat_id, context, casa):
    db["stats"]["clicks"][casa] = db["stats"]["clicks"].get(casa, 0) + 1
    await save_db_async()

    texto = db["config"].get(f"texto_{casa}", "📈 Entrada disponível")
    foto = db["config"].get(f"foto_{casa}")
    link = db["config"].get(casa, "https://google.com")

    keyboard = [[InlineKeyboardButton("💰 APOSTAR", url=link)]]

    if foto:
        try:
            await context.bot.send_photo(
                chat_id,
                foto,
                caption=texto,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # Fallback caso o file_id da foto seja inválido/antigo
            await context.bot.send_message(
                chat_id,
                texto,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await context.bot.send_message(
            chat_id,
            texto,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    delay = db["config"].get("delay_confirmacao", 20)
    await asyncio.sleep(delay)

    keyboard = [[
        InlineKeyboardButton(
            db["config"].get("confirmar_botao", "✅ Já fiz a aposta"),
            callback_data=f"confirmou_{casa}"
        )
    ]]

    await context.bot.send_message(
        chat_id,
        "👇 Clique abaixo quando finalizar",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================================================
# HANDLER DE CALLBACKS (BOTÕES)
# =========================================================

async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    chat_id = query.message.chat.id
    data = query.data

    if data in ["betmgm", "novibet", "jonbet"]:
        await fluxo(chat_id, context, data)

    elif data.startswith("confirmou_"):
        casa = data.replace("confirmou_", "")
        nome = query.from_user.first_name

        db["confirmacoes"][str(uid)] = {
            "nome": nome,
            "username": query.from_user.username,
            "casa": casa,
            "prints": [],
            "status": "aguardando_prints",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        db["stats"]["pendentes"] += 1
        await save_db_async()

        user_state[uid] = "aguardando_prints"

        # Substituição limpa de variáveis nas strings
        c_cfg = db["config"]
        await context.bot.send_message(chat_id, c_cfg["confirm_msg1"].format(nome=nome))
        await context.bot.send_message(chat_id, c_cfg["confirm_msg2"].format(nome=nome))
        await context.bot.send_message(chat_id, c_cfg["confirm_msg3"].format(nome=nome))
        await context.bot.send_message(chat_id, c_cfg["confirm_msg4"].format(nome=nome))

    elif data == "menu_config":
        keyboard = [
            [InlineKeyboardButton("🎤 Audio Start", callback_data="edit_audio_start")],
            [InlineKeyboardButton("🖼️ Foto Start", callback_data="edit_foto_start")],
            [InlineKeyboardButton("📝 Texto Start", callback_data="edit_texto_start")],
            [InlineKeyboardButton("📋 Texto Menu", callback_data="edit_menu_start")],
            [InlineKeyboardButton("✅ Configuração Confirmação", callback_data="menu_confirm")]
        ]
        await context.bot.send_message(chat_id, "⚙️ CONFIGURAÇÕES", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_confirm":
        keyboard = [
            [InlineKeyboardButton("📝 Mensagem 1", callback_data="edit_confirm_msg1")],
            [InlineKeyboardButton("📝 Mensagem 2", callback_data="edit_confirm_msg2")],
            [InlineKeyboardButton("📝 Mensagem 3", callback_data="edit_confirm_msg3")],
            [InlineKeyboardButton("📝 Mensagem 4", callback_data="edit_confirm_msg4")],
            [InlineKeyboardButton("✏️ Texto Botão", callback_data="edit_confirmar_botao")],
            [InlineKeyboardButton("⏱️ Delay", callback_data="edit_delay")]
        ]
        await context.bot.send_message(chat_id, "✅ CONFIGURAÇÃO CONFIRMAÇÃO", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_casas":
        keyboard = [
            [InlineKeyboardButton("🎰 BetMGM", callback_data="casa_betmgm")],
            [InlineKeyboardButton("🎰 Novibet", callback_data="casa_novibet")],
            [InlineKeyboardButton("🎰 Jonbet", callback_data="casa_jonbet")]
        ]
        await context.bot.send_message(chat_id, "📤 Enviar aposta", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("casa_"):
        casa = data.replace("casa_", "")
        keyboard = [
            [InlineKeyboardButton("✏️ Editar Texto", callback_data=f"edit_texto_{casa}")],
            [InlineKeyboardButton("🖼️ Editar Foto", callback_data=f"edit_foto_{casa}")],
            [InlineKeyboardButton("🔗 Editar Link", callback_data=f"edit_link_{casa}")],
            [InlineKeyboardButton("🟢 Ativar/Desativar", callback_data=f"toggle_{casa}")],
            [InlineKeyboardButton("👀 Testar Casa", callback_data=f"teste_{casa}")]
        ]
        await context.bot.send_message(chat_id, f"⚙️ {casa.upper()}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("toggle_"):
        casa = data.replace("toggle_", "")
        campo = f"ativo_{casa}"
        atual = db["config"].get(campo, True)
        db["config"][campo] = not atual
        await save_db_async()
        status = "ATIVADA" if not atual else "DESATIVADA"
        await context.bot.send_message(chat_id, f"✅ Casa {status}")

    elif data.startswith("teste_") and data.replace("teste_", "") in ["betmgm", "novibet", "jonbet"]:
        casa = data.replace("teste_", "")
        await fluxo(chat_id, context, casa)

    elif data == "menu_stats":
        keyboard = [
            [InlineKeyboardButton("📈 Ver Estatísticas", callback_data="ver_stats")],
            [InlineKeyboardButton("🗑 Resetar Estatísticas", callback_data="reset_stats")]
        ]
        await query.edit_message_text("📊 PAINEL DE ESTATÍSTICAS", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "ver_stats":
        stats = db["stats"]
        texto = (
            f"📊 ESTATÍSTICAS\n\n"
            f"👥 Usuários: {len(db['users'])}\n\n"
            f"🎰 BetMGM: {stats['clicks'].get('betmgm', 0)}\n"
            f"🎰 Novibet: {stats['clicks'].get('novibet', 0)}\n"
            f"🎰 Jonbet: {stats['clicks'].get('jonbet', 0)}\n\n"
            f"✅ Confirmados: {stats['confirmacoes']}\n"
            f"❌ Recusados: {stats['recusados']}\n"
            f"⏳ Pendentes: {stats['pendentes']}\n"
            f"💰 Reembolsados: {stats['reembolsados']}"
        )
        await query.edit_message_text(texto)
        
    elif data == "reset_stats":
        db["stats"]["clicks"] = {"betmgm": 0, "novibet": 0, "jonbet": 0}
        db["stats"]["confirmacoes"] = 0
        db["stats"]["recusados"] = 0
        db["stats"]["pendentes"] = 0
        db["stats"]["reembolsados"] = 0
        await save_db_async()
        await query.edit_message_text("🗑 Estatísticas resetadas com sucesso.")

    elif data == "menu_disparos":
        user_state[uid] = "broadcast"
        await context.bot.send_message(chat_id, "📢 Envie a mensagem do disparo")

    elif data == "export_csv":
        export_csv()
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "rb") as file:
                await context.bot.send_document(chat_id, file, filename="confirmados.csv")

    elif data.startswith("aprovar_"):
        target_uid = int(data.split("_")[1])
        confirmacao = db["confirmacoes"].get(str(target_uid))

        if not confirmacao:
             return

        if confirmacao.get("status") == "confirmado":
            await query.answer("Este usuário já foi aprovado!")
            return
            
        if confirmacao.get("status") == "pendente" and db["stats"]["pendentes"] > 0:
            db["stats"]["pendentes"] -= 1

        confirmacao["status"] = "confirmado"
        db["stats"]["confirmacoes"] += 1
        await save_db_async()

        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text="✨ Confirmação aprovada com sucesso!\n\nSua entrada já foi validada 💖"
            )
        except Exception:
            pass

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Reembolsado", callback_data=f"reembolsado_{target_uid}")]
        ])

        await query.edit_message_text(
            f"✅ APROVADO\n\n👤 {confirmacao['nome']}\n🆔 {target_uid}\n🎰 {confirmacao['casa']}\n📅 {confirmacao['data']}",
            reply_markup=keyboard
        )

    elif data.startswith("reembolsado_"):
        target_uid = int(data.split("_")[1])
        confirmacao = db["confirmacoes"].get(str(target_uid))

        if not confirmacao or confirmacao.get("status") == "reembolsado":
            return

        confirmacao["status"] = "reembolsado"
        db["stats"]["reembolsados"] += 1
        await save_db_async()

        await query.edit_message_text(
            f"💰 REEMBOLSADO\n\n👤 {confirmacao['nome']}\n🆔 {target_uid}\n🎰 {confirmacao['casa']}\n📅 {confirmacao['data']}"
        )
    
    elif data.startswith("recusar_"):
        alvo = data.replace("recusar_", "")
        if alvo in db["confirmacoes"]:
            db["confirmacoes"][alvo]["status"] = "recusado"
            db["stats"]["recusados"] += 1
            if db["stats"]["pendentes"] > 0:
                db["stats"]["pendentes"] -= 1
            await save_db_async()

            try:
                await context.bot.send_message(int(alvo), "❌ Sua confirmação foi RECUSADA")
            except Exception:
                pass
            await context.bot.send_message(chat_id, "❌ Usuário recusado")

# =========================================================
# ADMIN & MENSAGENS
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    if admin_logged(uid):
        keyboard = [
            [InlineKeyboardButton("⚙️ Configurações", callback_data="menu_config")],
            [InlineKeyboardButton("📤 Enviar aposta", callback_data="menu_casas")],
            [InlineKeyboardButton("📢 Disparos", callback_data="menu_disparos")],
            [InlineKeyboardButton("📊 Estatísticas", callback_data="menu_stats")],
            [InlineKeyboardButton("📥 Exportar CSV", callback_data="export_csv")]
        ]
        await update.message.reply_text("⚙️ PAINEL ADMIN", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    admin_session[uid] = "waiting_password"
    await update.message.reply_text("🔐 Digite a senha do admin")

async def mensagens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    if not msg:
        return

    # LOGIN ADMIN
    if admin_session.get(uid) == "waiting_password":
        if not msg.text:
            return
        senha = hashlib.sha256(msg.text.encode()).hexdigest()
        if senha == ADMIN_PASSWORD_HASH:
            admin_session[uid] = {"time": time.time()}
            await msg.reply_text("✅ Login realizado")
            keyboard = [
                [InlineKeyboardButton("⚙️ Configurações", callback_data="menu_config")],
                [InlineKeyboardButton("📤 Enviar aposta", callback_data="menu_casas")],
                [InlineKeyboardButton("📢 Disparos", callback_data="menu_disparos")],
                [InlineKeyboardButton("📊 Estatísticas", callback_data="menu_stats")],
                [InlineKeyboardButton("📥 Exportar CSV", callback_data="export_csv")]
            ]
            await msg.reply_text("⚙️ PAINEL ADMIN", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await msg.reply_text("❌ Senha incorreta")
        return

    # BROADCAST
    if user_state.get(uid) == "broadcast":
        if not msg.text:
            return
        enviados = 0
        for user in db["users"]:
            try:
                await context.bot.send_message(user, msg.text)
                enviados += 1
                await asyncio.sleep(0.05)  # Evita atingir o limite de spam do TG
            except Exception:
                pass
        user_state.pop(uid, None)
        await msg.reply_text(f"✅ Disparo enviado para {enviados} usuários")
        return

    # EDIÇÕES DE CONFIGURAÇÃO
    if uid in user_state and user_state.get(uid) != "aguardando_prints":
        campo = user_state[uid]

        if msg.photo:
            db["config"][campo] = msg.photo[-1].file_id
        elif msg.voice:
            db["config"][campo] = msg.voice.file_id
        elif msg.text:
            if campo == "delay_confirmacao":
                if not msg.text.isdigit():
                    await msg.reply_text("❌ Envie apenas números")
                    return
                db["config"][campo] = int(msg.text)
            else:
                db["config"][campo] = msg.text
        else:
            return

        await save_db_async()
        user_state.pop(uid, None)
        await msg.reply_text("✅ Atualizado com sucesso")
        return

    # RECEBIMENTO DE PRINTS
    if user_state.get(uid) == "aguardando_prints":
        if not msg.photo:
            await msg.reply_text("⚠️ Envie imagens")
            return

        confirmacao = db["confirmacoes"].get(str(uid))
        if not confirmacao:
            return

        file_id = msg.photo[-1].file_id
        if file_id in confirmacao["prints"]:
            await msg.reply_text("⚠️ Print duplicado")
            return

        confirmacao["prints"].append(file_id)
        await save_db_async()
        quantidade = len(confirmacao["prints"])
        await msg.reply_text(f"📸 Print {quantidade}/2 recebido")

        if quantidade >= 2:
            user_state.pop(uid, None)
            confirmacao["status"] = "pendente"
            await save_db_async()
            await msg.reply_text("⏳ Prints enviados para análise")

            SUPORTE_GROUP_ID = -1003827624203
            texto = (
                f"⚠️ NOVA CONFIRMAÇÃO\n\n"
                f"👤 {confirmacao['nome']}\n"
                f"🆔 {uid}\n"
                f"🎰 {confirmacao['casa']}\n"
                f"📅 {confirmacao['data']}"
            )
            keyboard = [[
                InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar_{uid}"),
                InlineKeyboardButton("❌ Recusar", callback_data=f"recusar_{uid}"),
                InlineKeyboardButton("💰 Reembolsado", callback_data=f"reembolsado_{uid}")
            ]]

            try:
                await context.bot.send_message(SUPORTE_GROUP_ID, texto, reply_markup=InlineKeyboardMarkup(keyboard))
                for foto in confirmacao["prints"]:
                    await context.bot.send_photo(SUPORTE_GROUP_ID, foto)
            except Exception as e:
                print(f"❌ Erro ao enviar mídias para o grupo de suporte: {e}")

# =========================================================
# CALLBACK HANDLERS ADICIONAIS
# =========================================================

async def callback_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = query.from_user.id
    chat_id = query.message.chat.id

    if data.startswith("edit_"):
        campo = data.replace("edit_", "")
        if campo.startswith("link_"):
            campo = campo.replace("link_", "")
            texto = "🔗 Envie o novo link"
        elif "texto" in campo or "msg" in campo:
            texto = "📝 Envie o novo texto"
        elif "foto" in campo:
            texto = "🖼️ Envie a nova foto"
        elif "audio" in campo:
            texto = "🎤 Envie o novo áudio"
        elif campo == "delay":
            campo = "delay_confirmacao"
            texto = "⏱️ Envie o delay em segundos"
        else:
            texto = "✏️ Envie o novo valor"

        user_state[uid] = campo
        await context.bot.send_message(chat_id, texto)

# =========================================================
# WEB SERVER MICRO (EVITA TIMEOUT NO RENDER)
# =========================================================

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  # Desativa logs excessivos de requisições web no terminal

def run_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌍 Servidor de Health Check rodando na porta {port}")
    server.serve_forever()

# =========================================================
# INICIALIZAÇÃO DO APP
# =========================================================

if __name__ == "__main__":
    # Inicia o servidor web falso em segundo plano para o Render não derrubar o bot
    web_thread = threading.Thread(target=run_health_server, daemon=True)
    web_thread.start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callback_extra, pattern="^edit_"))
    app.add_handler(CallbackQueryHandler(botoes))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VOICE, mensagens))

    async def main():
        print("🚀 BOT PROFISSIONAL PRONTO PARA O RENDER")
        # Inicializa o aplicativo do Telegram de forma assíncrona correta
        await app.initialize()
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
    
        # Mantém o bot rodando indefinitivamente
        while True:
            await asyncio.sleep(3600)

    if __name__ == "__main__":
        # Inicia o servidor web falso em segundo plano para o Render não derrubar o bot
        web_thread = threading.Thread(target=run_health_server, daemon=True)
        web_thread.start()

        # Cria e roda o loop de eventos explicitamente, resolvendo o erro do Python 3.14
        asyncio.run(main())
