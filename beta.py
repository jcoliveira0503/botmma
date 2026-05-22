import json
import asyncio
import os
import hashlib
import csv
import time
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
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN", "8750623179:AAGlOXpREIHoinX_eXc2mXbPMjDouwHgJzU")

ADMIN_IDS = [7188888143, 1348107174]

ADMIN_PASSWORD_HASH = hashlib.sha256(
    "luansantana".encode()
).hexdigest()

SESSION_TIME = 1800

DB_FILE = "db.json"
CSV_FILE = "confirmados.csv"

admin_session = {}
login_attempts = {}
user_state = {}

# =========================================================
# DB
# =========================================================

DEFAULT_DB = {
    "users": [],

    "confirmacoes": {},

    "stats": {
        "confirmacoes": 0,
        "recusados": 0,
        "pendentes": 0,
        "reembolsados": 0,
        
        "clicks": {
            "betmgm": 0,
            "novibet": 0,
            "jonbet": 0
        }
    },

    "config": {

        # START
        "texto_start": "🔥 Bem-vindo ao sistema!",
        "menu_start": "👇 Escolha uma casa:",

        # CONFIRMAÇÃO
        "confirm_msg1": "🔥 Fechou, {nome}! Tá na aposta",
        "confirm_msg2": "📈 Agora acompanhe o jogo",
        "confirm_msg3": "🍀 Boa sorte {nome}",
        "confirm_msg4": "📸 Envie 2 prints da aposta",

        "confirmar_botao": "✅ Já fiz a aposta",

        "delay_confirmacao": 20,

        # CASAS
        "ativo_betmgm": True,
        "ativo_novibet": True,
        "ativo_jonbet": True,

        "nome_betmgm": "🎰 BetMGM",
        "nome_novibet": "🎰 Novibet",
        "nome_jonbet": "🎰 Jonbet",

        # LINKS
        "betmgm": "https://google.com",
        "novibet": "https://google.com",
        "jonbet": "https://google.com",

        # TEXTOS CASAS
        "texto_betmgm": "🔥 Entrada disponível na BetMGM",
        "texto_novibet": "🔥 Entrada disponível na Novibet",
        "texto_jonbet": "🔥 Entrada disponível na Jonbet"
    }
}


def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_DB


def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)


db = load_db()

# =========================================================
# HELPERS
# =========================================================


def add_user(uid):
    if uid not in db["users"]:
        db["users"].append(uid)
        save_db()


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

    if db["config"].get("ativo_betmgm"):
        keyboard.append([
            InlineKeyboardButton(
                db["config"]["nome_betmgm"],
                callback_data="betmgm"
            )
        ])

    if db["config"].get("ativo_novibet"):
        keyboard.append([
            InlineKeyboardButton(
                db["config"]["nome_novibet"],
                callback_data="novibet"
            )
        ])

    if db["config"].get("ativo_jonbet"):
        keyboard.append([
            InlineKeyboardButton(
                db["config"]["nome_jonbet"],
                callback_data="jonbet"
            )
        ])

    return InlineKeyboardMarkup(keyboard)


def export_csv():

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:

        writer = csv.writer(file)

        writer.writerow([
            "id",
            "nome",
            "username",
            "casa",
            "status",
            "data"
        ])

        for uid, dados in db["confirmacoes"].items():

            writer.writerow([
                uid,
                dados.get("nome"),
                dados.get("username"),
                dados.get("casa"),
                dados.get("status"),
                dados.get("data")
            ])

# =========================================================
# START
# =========================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    chat_id = update.effective_chat.id

    add_user(uid)

    await context.bot.send_message(
        chat_id,
        db["config"]["texto_start"]
    )

    await context.bot.send_message(
        chat_id,
        db["config"]["menu_start"],
        reply_markup=start_keyboard()
    )

# =========================================================
# FLUXO
# =========================================================


async def fluxo(chat_id, context, casa):

    db["stats"]["clicks"][casa] += 1

    save_db()

    texto = db["config"].get(
        f"texto_{casa}",
        "📈 Entrada disponível"
    )

    foto = db["config"].get(
        f"foto_{casa}"
    )

    link = db["config"].get(casa)

    keyboard = [
        [
            InlineKeyboardButton(
                "💰 APOSTAR",
                url=link
            )
        ]
    ]

    if foto:

        await context.bot.send_photo(
            chat_id,
            foto,
            caption=texto,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:

        await context.bot.send_message(
            chat_id,
            texto,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await asyncio.sleep(
        db["config"].get(
            "delay_confirmacao",
            20
        )
    )

    keyboard = [
        [
            InlineKeyboardButton(
                db["config"]["confirmar_botao"],
                callback_data=f"confirmou_{casa}"
            )
        ]
    ]

    await context.bot.send_message(
        chat_id,
        "👇 Clique abaixo quando finalizar",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================================================
# TESTES
# =========================================================


async def teste_start(chat_id, context):

    await context.bot.send_message(
        chat_id,
        db["config"]["texto_start"]
    )

    await context.bot.send_message(
        chat_id,
        db["config"]["menu_start"],
        reply_markup=start_keyboard()
    )


async def teste_fluxo(chat_id, context):

    await context.bot.send_message(
        chat_id,
        "🧪 TESTE FLUXO COMPLETO"
    )

    await fluxo(chat_id, context, "betmgm")

# =========================================================
# CALLBACKS
# =========================================================


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    uid = query.from_user.id
    chat_id = query.message.chat.id

    data = query.data

    # =====================================================
    # CASAS USUÁRIO
    # =====================================================

    if data in ["betmgm", "novibet", "jonbet"]:

        await fluxo(chat_id, context, data)

    # =====================================================
    # CONFIRMAÇÃO
    # =====================================================

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

        save_db()

        user_state[uid] = "aguardando_prints"

        msg1 = db["config"]["confirm_msg1"].replace("{nome}", nome)
        msg2 = db["config"]["confirm_msg2"].replace("{nome}", nome)
        msg3 = db["config"]["confirm_msg3"].replace("{nome}", nome)
        msg4 = db["config"]["confirm_msg4"].replace("{nome}", nome)

        await context.bot.send_message(chat_id, msg1)
        await context.bot.send_message(chat_id, msg2)
        await context.bot.send_message(chat_id, msg3)
        await context.bot.send_message(chat_id, msg4)

    # =====================================================
    # CONFIG
    # =====================================================

    elif data == "menu_config":

        keyboard = [

            [InlineKeyboardButton("🎤 Audio Start", callback_data="edit_audio_start")],

            [InlineKeyboardButton("🖼️ Foto Start", callback_data="edit_foto_start")],

            [InlineKeyboardButton("📝 Texto Start", callback_data="edit_texto_start")],

            [InlineKeyboardButton("📋 Texto Menu", callback_data="edit_menu_start")],

            [InlineKeyboardButton("🎤 Áudio Global", callback_data="edit_audio_global")],

            [InlineKeyboardButton("✅ Configuração Confirmação", callback_data="menu_confirm")]
        ]

        await context.bot.send_message(
            chat_id,
            "⚙️ CONFIGURAÇÕES",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =====================================================
    # CONFIG CONFIRMAÇÃO
    # =====================================================

    elif data == "menu_confirm":

        keyboard = [

            [InlineKeyboardButton("📝 Mensagem 1", callback_data="edit_confirm_msg1")],

            [InlineKeyboardButton("📝 Mensagem 2", callback_data="edit_confirm_msg2")],

            [InlineKeyboardButton("📝 Mensagem 3", callback_data="edit_confirm_msg3")],

            [InlineKeyboardButton("📝 Mensagem 4", callback_data="edit_confirm_msg4")],

            [InlineKeyboardButton("✏️ Texto Botão", callback_data="edit_confirmar_botao")],

            [InlineKeyboardButton("⏱️ Delay", callback_data="edit_delay")]
        ]

        await context.bot.send_message(
            chat_id,
            "✅ CONFIGURAÇÃO CONFIRMAÇÃO",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =====================================================
    # 7CASAS
    # =====================================================

    elif data == "menu_casas":

        keyboard = [

            [InlineKeyboardButton("🎰 BetMGM", callback_data="casa_betmgm")],

            [InlineKeyboardButton("🎰 Novibet", callback_data="casa_novibet")],

            [InlineKeyboardButton("🎰 Jonbet", callback_data="casa_jonbet")]
        ]

        await context.bot.send_message(
            chat_id,
            "📤 Enviar aposta",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("casa_"):

        casa = data.replace("casa_", "")

        keyboard = [

            [InlineKeyboardButton("✏️ Editar Texto", callback_data=f"edit_texto_{casa}")],

            [InlineKeyboardButton("🖼️ Editar Foto", callback_data=f"edit_foto_{casa}")],

            [InlineKeyboardButton("🔗 Editar Link", callback_data=f"edit_link_{casa}")],

            [InlineKeyboardButton("🟢 Ativar/Desativar", callback_data=f"toggle_{casa}")],

            [InlineKeyboardButton("👀 Testar Casa", callback_data=f"teste_{casa}")]
        ]

        await context.bot.send_message(
            chat_id,
            f"⚙️ {casa.upper()}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("toggle_"):

        casa = data.replace("toggle_", "")

        campo = f"ativo_{casa}"

        atual = db["config"].get(campo, True)

        db["config"][campo] = not atual

        save_db()

        status = "ATIVADA" if not atual else "DESATIVADA"

        await context.bot.send_message(
            chat_id,
            f"✅ Casa {status}"
        )

    elif data in ["teste_betmgm", "teste_novibet", "teste_jonbet"]:

        casa = data.replace("teste_", "")

        await fluxo(chat_id, context, casa)

    # =====================================================
    # MENU ESTATÍSTICAS
    # =====================================================

    elif data == "menu_stats":

        keyboard = [

            [
                InlineKeyboardButton(
                    "📈 Ver Estatísticas",
                    callback_data="ver_stats"
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 Resetar Estatísticas",
                    callback_data="reset_stats"
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Voltar",
                    callback_data="admin"
                )
            ]
        ]

        await query.edit_message_text(
            "📊 PAINEL DE ESTATÍSTICAS",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "ver_stats":

        stats = db["stats"]

        texto = (
            f"📊 ESTATÍSTICAS\n\n"

            f"👥 Usuários: {len(db['users'])}\n\n"

            f"🎰 BetMGM: {stats['clicks']['betmgm']}\n"

            f"🎰 Novibet: {stats['clicks']['novibet']}\n"

            f"🎰 Jonbet: {stats['clicks']['jonbet']}\n\n"

            f"✅ Confirmados: {stats['confirmacoes']}\n"

            f"❌ Recusados: {stats['recusados']}\n"

            f"⏳ Pendentes: {stats['pendentes']}\n"
            
            f"💰 Reembolsados: {stats['reembolsados']}"
        )

        await query.edit_message_text(texto)
        
    elif data == "reset_stats":

        db["stats"]["clicks"] = {
            "betmgm": 0,
            "novibet": 0,
            "jonbet": 0
        }

        db["stats"]["confirmacoes"] = 0

        db["stats"]["recusados"] = 0

        db["stats"]["pendentes"] = 0
        
        db["stats"]["reembolsados"] = 0

        save_db()

        await query.edit_message_text(
            "🗑 Estatísticas resetadas com sucesso."
        )

    # =====================================================
    # TESTES
    # =====================================================

    elif data == "menu_testes":

        keyboard = [

            [InlineKeyboardButton("👀 Testar Start", callback_data="teste_start")],

            [InlineKeyboardButton("🔥 Testar Fluxo Completo", callback_data="teste_fluxo")]
        ]

        await context.bot.send_message(
            chat_id,
            "🧪 TESTES",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "teste_start":

        await teste_start(chat_id, context)

    elif data == "teste_fluxo":

        await teste_fluxo(chat_id, context)

    # =====================================================
    # DISPAROS
    # =====================================================

    elif data == "menu_disparos":

        user_state[uid] = "broadcast"

        await context.bot.send_message(
            chat_id,
            "📢 Envie a mensagem do disparo"
        )

    # =====================================================
    # EXPORT CSV
    # =====================================================

    elif data == "export_csv":

        export_csv()

        with open(CSV_FILE, "rb") as file:

            await context.bot.send_document(
                chat_id,
                file,
                filename="confirmados.csv"
            )

    # =====================================================
    # APROVAR (CORRIGIDO)
    # =====================================================
    if data.startswith("aprovar_"):
        uid = int(data.split("_")[1])
        confirmacao = db["confirmacoes"].get(str(uid))

        if not confirmacao:
             return

        # 1. Verifica se já não foi aprovado antes para não contar duplicado
        if confirmacao.get("status") == "confirmado":
            await query.answer("Este usuário já foi aprovado!")
            return
            
        # 2. Se o status atual for pendente, AGORA SIM removemos dos pendentes
        if confirmacao.get("status") == "pendente":
            if db["stats"]["pendentes"] > 0:
                db["stats"]["pendentes"] -= 1

        # 3. Atualiza para confirmado
        confirmacao["status"] = "confirmado"
        db["stats"]["confirmacoes"] += 1
        
        save_db()

        # MENSAGEM PARA O USUÁRIO
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="✨ Confirmação aprovada com sucesso!\n\nSua entrada já foi validada 💖"
            )
        except:
            pass # Caso o usuário tenha bloqueado o bot

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Reembolsado", callback_data=f"reembolsado_{uid}")]
        ])

        await query.edit_message_text(
            f"✅ APROVADO\n\n"
            f"👤 {confirmacao['nome']}\n"
            f"🆔 {uid}\n"
            f"🎰 {confirmacao['casa']}\n"
            f"📅 {confirmacao['data']}",
            reply_markup=keyboard
        )



# =====================================================
# REEMBOLSADO
# =====================================================

    if data.startswith("reembolsado_"):

        uid = int(data.split("_")[1])

        confirmacao = db["confirmacoes"].get(str(uid))

        if not confirmacao:
            return

        if confirmacao.get("status") == "reembolsado":
            return

        db["stats"]["reembolsados"] += 1
        
        save_db()

        await query.edit_message_text(
            f"💰 REEMBOLSADO\n\n"
            f"👤 {confirmacao['nome']}\n"
            f"🆔 {uid}\n"
            f"🎰 {confirmacao['casa']}\n"
            f"📅 {confirmacao['data']}"
        )
    
    # =====================================================
    # RECUSAR
    # =====================================================

    elif data.startswith("recusar_"):

        alvo = data.replace("recusar_", "")

        if alvo in db["confirmacoes"]:

            db["confirmacoes"][alvo]["status"] = "recusado"

            db["stats"]["recusados"] += 1
            db["stats"]["pendentes"] -= 1

            save_db()

            await context.bot.send_message(
                int(alvo),
                "❌ Sua confirmação foi RECUSADA"
            )

            await context.bot.send_message(
                chat_id,
                "❌ Usuário recusado"
            )

# =========================================================
# ADMIN
# =========================================================


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not is_admin(uid):
        return

    agora = time.time()

    if uid in admin_session and isinstance(admin_session[uid], dict):

        if agora - admin_session[uid]["time"] < SESSION_TIME:

            keyboard = [

                [InlineKeyboardButton("⚙️ Configurações", callback_data="menu_config")],

                [InlineKeyboardButton("📤 Enviar aposta", callback_data="menu_casas")],

                [InlineKeyboardButton("📢 Disparos", callback_data="menu_disparos")],

                [InlineKeyboardButton("📊 Estatísticas", callback_data="menu_stats")],

                [InlineKeyboardButton("🧪 Testes", callback_data="menu_testes")],

                [InlineKeyboardButton("📥 Exportar CSV", callback_data="export_csv")]
            ]

            await update.message.reply_text(
                "⚙️ PAINEL ADMIN",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            return

    admin_session[uid] = "waiting_password"

    await update.message.reply_text(
        "🔐 Digite a senha do admin"
    )

# =========================================================
# MENSAGENS
# =========================================================


async def mensagens(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    msg = update.message


        
    # =====================================================
    # LOGIN ADMIN
    # =====================================================

    if admin_session.get(uid) == "waiting_password":

        senha = hashlib.sha256(
            msg.text.encode()
        ).hexdigest()

        if senha == ADMIN_PASSWORD_HASH:

            admin_session[uid] = {
                "time": time.time()
            }

            await msg.reply_text(
                "✅ Login realizado"
            )

            keyboard = [

                [InlineKeyboardButton("⚙️ Configurações", callback_data="menu_config")],

                [InlineKeyboardButton("📤 Enviar aposta", callback_data="menu_casas")],

                [InlineKeyboardButton("📢 Disparos", callback_data="menu_disparos")],

                [InlineKeyboardButton("📊 Estatísticas", callback_data="menu_stats")],

                [InlineKeyboardButton("🧪 Testes", callback_data="menu_testes")],

                [InlineKeyboardButton("📥 Exportar CSV", callback_data="export_csv")]
            ]

            await msg.reply_text(
                "⚙️ PAINEL ADMIN",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        else:

            await msg.reply_text(
                "❌ Senha incorreta"
            )

        return

    # =====================================================
    # BROADCAST
    # =====================================================

    if user_state.get(uid) == "broadcast":

        enviados = 0

        for user in db["users"]:

            try:

                await context.bot.send_message(
                    user,
                    msg.text
                )

                enviados += 1

                await asyncio.sleep(0.05)

            except:
                pass

        user_state.pop(uid, None)

        await msg.reply_text(
            f"✅ Disparo enviado para {enviados} usuários"
        )

        return

    # =====================================================
    # EDIÇÕES
    # =====================================================

    if uid in user_state and user_state.get(uid) != "aguardando_prints":

        campo = user_state[uid]

        # FOTO
        if msg.photo:

            db["config"][campo] = msg.photo[-1].file_id

            save_db()

            user_state.pop(uid, None)

            await msg.reply_text(
                "✅ Foto atualizada"
            )

            return

        # ÁUDIO
        elif msg.voice:

            db["config"][campo] = msg.voice.file_id

            save_db()

            user_state.pop(uid, None)

            await msg.reply_text(
                "✅ Áudio atualizado"
            )

            return

        # TEXTO
        elif msg.text:

            if campo == "delay_confirmacao":

                try:

                    db["config"][campo] = int(msg.text)

                except:

                    await msg.reply_text(
                        "❌ Envie apenas números"
                    )

                    return

            else:

                db["config"][campo] = msg.text

            save_db()

            user_state.pop(uid, None)

            await msg.reply_text(
                "✅ Atualizado com sucesso"
            )

            return

    # =====================================================
    # PRINTS
    # =====================================================

    if isinstance(user_state, dict) and user_state.get(uid) == "aguardando_prints":

        if not msg.photo:

            await msg.reply_text(
                "⚠️ Envie imagens"
            )

            return

        confirmacao = db["confirmacoes"].get(str(uid))

        if not confirmacao:
            return

        file_id = msg.photo[-1].file_id

# ANTI DUPLICADO
        if file_id in confirmacao["prints"]:

            await msg.reply_text(
                "⚠️ Print duplicado"
            )

            return

        confirmacao["prints"].append(file_id)

        save_db()

        quantidade = len(confirmacao["prints"])

        await msg.reply_text(
            f"📸 Print {quantidade}/2 recebido"
        )

        if quantidade >= 2:

            user_state.pop(uid, None)

            confirmacao["status"] = "pendente"

            save_db()

            await msg.reply_text(
                "⏳ Prints enviados para análise"
            )

            SUPORTE_GROUP_ID = -1003827624203

            texto = (
                f"⚠️ NOVA CONFIRMAÇÃO\n\n"
                f"👤 {confirmacao['nome']}\n"
                f"🆔 {uid}\n"
                f"🎰 {confirmacao['casa']}\n"
                f"📅 {confirmacao['data']}"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Aprovar",
                        callback_data=f"aprovar_{uid}"
                    ),

                    InlineKeyboardButton(
                        "❌ Recusar",
                        callback_data=f"recusar_{uid}"
                    ),

                    InlineKeyboardButton(
                        "💰 Reembolsado",
                        callback_data=f"reembolsado_{uid}"
                    )
                ]
            ]

            await context.bot.send_message(
                SUPORTE_GROUP_ID,
                texto,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            for foto in confirmacao["prints"]:

                await context.bot.send_photo(
                    SUPORTE_GROUP_ID,
                    foto
                )
# =========================================================
# EDIT CALLBACKS
# =========================================================


async def edit_handler(data, chat_id, context, uid):

    campo = data.replace("edit_", "")

    # LINKS
    if campo.startswith("link_"):

        casa = campo.replace("link_", "")

        campo = casa

        texto = "🔗 Envie o novo link"

    # TEXTO
    elif "texto" in campo or "msg" in campo:

        texto = "📝 Envie o novo texto"

    # FOTO
    elif "foto" in campo:

        texto = "🖼️ Envie a nova foto"

    # ÁUDIO
    elif "audio" in campo:

        texto = "🎤 Envie o novo áudio"

    # DELAY
    elif campo == "delay":

        campo = "delay_confirmacao"

        texto = "⏱️ Envie o delay em segundos"

    else:

        texto = "✏️ Envie o novo valor"

    user_state[uid] = campo

    await context.bot.send_message(
        chat_id,
        texto
    )

# =========================================================
# CALLBACK EXTRA
# =========================================================


async def callback_extra(update, context):

    query = update.callback_query

    data = query.data

    if data.startswith("edit_"):

        await edit_handler(
            data,
            query.message.chat.id,
            context,
            query.from_user.id
        )

# =========================================================
# INIT
# =========================================================

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(60)
    .read_timeout(60)
    .write_timeout(60)
    .pool_timeout(60)
    .build()
)

app.add_handler(
    CommandHandler("start", start)
)

app.add_handler(
    CommandHandler("admin", admin)
)

app.add_handler(
    CallbackQueryHandler(callback_extra, pattern="^edit_")
)

app.add_handler(
    CallbackQueryHandler(botoes)
)

app.add_handler(
    MessageHandler(
        filters.TEXT |
        filters.PHOTO |
        filters.VOICE,
        mensagens
    )
)

print("🚀 BOT PROFISSIONAL RODANDO")

app.run_polling(
    drop_pending_updates=True,
    timeout=60
)