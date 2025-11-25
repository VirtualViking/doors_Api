import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from door_controller import DoorController
from database import Database

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ALLOWED_USERS = os.getenv('ALLOWED_USER_IDS', '').split(',')

# Credenciales de login
LOGIN_USERNAME = os.getenv('LOGIN_USERNAME', 'admin')
LOGIN_PASSWORD = os.getenv('LOGIN_PASSWORD', 'admin123')

class SlidingDoorBot:
    def __init__(self):
        self.door_controller = DoorController()
        self.db = Database()
        self.logged_users = {}  # Diccionario para usuarios logueados {user_id: True}
        self.awaiting_credentials = {}  # Usuarios esperando enviar credenciales
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - Mensaje de bienvenida"""
        user = update.effective_user
        
        if not self._is_authorized(user.id):
            await update.message.reply_text(
                "❌ No estás autorizado para usar este bot.\n"
                f"Tu ID: {user.id}"
            )
            return
        
        # Verificar si está logueado
        if not self._is_logged_in(user.id):
            await update.message.reply_text(
                f"👋 ¡Hola {user.first_name}!\n\n"
                "🔐 *Sistema de Control de Puertas*\n\n"
                "⚠️ Debes iniciar sesión para usar el bot.\n\n"
                "Usa el comando: /login",
                parse_mode='Markdown'
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("🚪 Abrir Puerta", callback_data="open_door"),
                InlineKeyboardButton("🔒 Cerrar Puerta", callback_data="close_door")
            ],
            [
                InlineKeyboardButton("📊 Estado", callback_data="status"),
                InlineKeyboardButton("📜 Registro", callback_data="history")
            ],
            [
                InlineKeyboardButton("🚪 Cerrar Sesión", callback_data="logout")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 ¡Hola {user.first_name}!\n\n"
            "🏠 *Sistema de Control de Puertas*\n\n"
            "✅ Sesión activa\n\n"
            "Selecciona una opción:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /login - Iniciar sesión"""
        user = update.effective_user
        
        if not self._is_authorized(user.id):
            await update.message.reply_text(
                "❌ No estás autorizado para usar este bot.\n"
                f"Tu ID: {user.id}"
            )
            return
        
        # Si ya está logueado
        if self._is_logged_in(user.id):
            await update.message.reply_text(
                "✅ Ya tienes una sesión activa.\n\n"
                "Usa /start para ver el menú."
            )
            return
        
        # Marcar que está esperando credenciales
        self.awaiting_credentials[user.id] = True
        
        await update.message.reply_text(
            "🔐 *Inicio de Sesión*\n\n"
            "Por favor envía tus credenciales en el formato:\n"
            "`usuario contraseña`\n\n"
            "Ejemplo: `admin micontraseña123`",
            parse_mode='Markdown'
        )
        
        logger.info(f"📝 Usuario {user.first_name} (ID: {user.id}) solicitó login")
    
    async def handle_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja las credenciales enviadas por el usuario"""
        user = update.effective_user
        
        # Solo procesar si está esperando credenciales
        if user.id not in self.awaiting_credentials:
            return
        
        message_text = update.message.text.strip()
        parts = message_text.split()
        
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ Formato incorrecto.\n\n"
                "Envía: `usuario contraseña`",
                parse_mode='Markdown'
            )
            return
        
        username, password = parts[0], parts[1]
        
        # Validar credenciales
        if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
            # Login exitoso
            self.logged_users[user.id] = True
            del self.awaiting_credentials[user.id]
            
            logger.info(f"✅ Usuario {user.first_name} (ID: {user.id}) inició sesión correctamente")
            
            await update.message.reply_text(
                "✅ *Inicio de Sesión Exitoso*\n\n"
                f"Bienvenido {user.first_name}!\n\n"
                "Usa /start para ver el menú de control.",
                parse_mode='Markdown'
            )
        else:
            # Login fallido
            logger.warning(f"❌ Intento de login fallido - Usuario: {user.first_name} (ID: {user.id}) - Credenciales: {username}/***")
            
            await update.message.reply_text(
                "❌ *Credenciales Incorrectas*\n\n"
                "Usuario o contraseña inválidos.\n\n"
                "Intenta nuevamente con /login",
                parse_mode='Markdown'
            )
            del self.awaiting_credentials[user.id]
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja las pulsaciones de botones"""
        query = update.callback_query
        user = query.from_user
        
        if not self._is_authorized(user.id):
            await query.answer("❌ No autorizado", show_alert=True)
            return
        
        # Verificar login para todas las acciones excepto logout
        if query.data != "logout" and not self._is_logged_in(user.id):
            await query.answer()
            await query.edit_message_text(
                "⚠️ *Sesión Expirada*\n\n"
                "Por favor inicia sesión nuevamente con /login",
                parse_mode='Markdown'
            )
            return
        
        await query.answer()
        
        action = query.data
        
        if action == "open_door":
            await self._handle_open_door(query, user)
        elif action == "close_door":
            await self._handle_close_door(query, user)
        elif action == "status":
            await self._handle_status(query)
        elif action == "history":
            await self._handle_history(query)
        elif action == "logout":
            await self._handle_logout(query, user)
        elif action == "back_menu":
            await self._show_main_menu(query)
    
    async def _handle_open_door(self, query, user):
        """Procesa la apertura de puerta"""
        try:
            logger.info(f"🚪 Usuario {user.first_name} está abriendo la puerta...")
            await query.edit_message_text("⏳ Abriendo puerta...")
            
            # Ejecutar apertura de puerta
            result = await self.door_controller.open_door()
            
            if result['success']:
                # Guardar en base de datos
                self.db.log_action(
                    user_id=user.id,
                    username=user.username or user.first_name,
                    action='open',
                    status='success'
                )
                
                message = (
                    "✅ *Puerta Abierta Exitosamente*\n\n"
                    f"👤 Usuario: {user.first_name}\n"
                    f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y')}\n\n"
                    "🚪 La puerta se cerrará automáticamente en 10 segundos."
                )
                
                keyboard = [[InlineKeyboardButton("🔙 Menú Principal", callback_data="back_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                # Programar notificación de cierre
                context = query._bot
                await self._schedule_auto_close(context, query.message.chat_id, user)
                
            else:
                raise Exception(result.get('error', 'Error desconocido'))
                
        except Exception as e:
            logger.error(f"Error abriendo puerta: {e}")
            self.db.log_action(
                user_id=user.id,
                username=user.username or user.first_name,
                action='open',
                status='error',
                error_message=str(e)
            )
            
            await query.edit_message_text(
                f"❌ *Error al abrir la puerta*\n\n"
                f"Detalles: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _handle_close_door(self, query, user):
        """Procesa el cierre de puerta"""
        try:
            logger.info(f"🔒 Usuario {user.first_name} está cerrando la puerta...")
            await query.edit_message_text("⏳ Cerrando puerta...")
            
            result = await self.door_controller.close_door()
            
            if result['success']:
                self.db.log_action(
                    user_id=user.id,
                    username=user.username or user.first_name,
                    action='close',
                    status='success'
                )
                
                message = (
                    "🔒 *Puerta Cerrada Exitosamente*\n\n"
                    f"👤 Usuario: {user.first_name}\n"
                    f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y')}"
                )
                
                keyboard = [[InlineKeyboardButton("🔙 Menú Principal", callback_data="back_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                raise Exception(result.get('error', 'Error desconocido'))
                
        except Exception as e:
            logger.error(f"Error cerrando puerta: {e}")
            self.db.log_action(
                user_id=user.id,
                username=user.username or user.first_name,
                action='close',
                status='error',
                error_message=str(e)
            )
            
            await query.edit_message_text(
                f"❌ *Error al cerrar la puerta*\n\n"
                f"Detalles: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _handle_status(self, query):
        """Muestra el estado actual del sistema"""
        logger.info("📊 Consultando estado del sistema...")
        status = await self.door_controller.get_status()
        
        door_icon = "🟢" if status['door_open'] else "🔴"
        door_state = "Abierta" if status['door_open'] else "Cerrada"
        
        message = (
            "📊 *Estado del Sistema*\n\n"
            f"{door_icon} Puerta: *{door_state}*\n"
            f"⚡ Sistema: {'Operativo' if status['system_ok'] else 'Error'}\n"
            f"🕐 Última actualización: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Menú Principal", callback_data="back_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_history(self, query):
        """Muestra el historial de acciones"""
        logger.info("📜 Consultando historial de acciones...")
        records = self.db.get_recent_actions(limit=10)
        
        if not records:
            message = "📜 *Registro*\n\nNo hay registros aún."
        else:
            message = "📜 *Registro de Acciones*\n\n"
            for record in records:
                icon = "✅" if record['status'] == 'success' else "❌"
                action_text = "Abrió" if record['action'] == 'open' else "Cerró"
                message += (
                    f"{icon} {action_text} - {record['username']}\n"
                    f"   🕐 {record['timestamp']}\n\n"
                )
        
        keyboard = [[InlineKeyboardButton("🔙 Menú Principal", callback_data="back_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_logout(self, query, user):
        """Cierra la sesión del usuario"""
        if user.id in self.logged_users:
            del self.logged_users[user.id]
            logger.info(f"🚪 Usuario {user.first_name} (ID: {user.id}) cerró sesión")
        
        await query.edit_message_text(
            "🚪 *Sesión Cerrada*\n\n"
            "Has cerrado sesión exitosamente.\n\n"
            "Usa /login para volver a iniciar sesión.",
            parse_mode='Markdown'
        )
    
    async def _show_main_menu(self, query):
        """Muestra el menú principal"""
        user = query.from_user
        
        keyboard = [
            [
                InlineKeyboardButton("🚪 Abrir Puerta", callback_data="open_door"),
                InlineKeyboardButton("🔒 Cerrar Puerta", callback_data="close_door")
            ],
            [
                InlineKeyboardButton("📊 Estado", callback_data="status"),
                InlineKeyboardButton("📜 Registro", callback_data="history")
            ],
            [
                InlineKeyboardButton("🚪 Cerrar Sesión", callback_data="logout")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🏠 *Sistema de Control de Puertas*\n\n"
            "Selecciona una opción:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _schedule_auto_close(self, bot, chat_id, user):
        """Programa el cierre automático de la puerta"""
        import asyncio
        await asyncio.sleep(10)
        
        result = await self.door_controller.close_door()
        
        if result['success']:
            self.db.log_action(
                user_id=user.id,
                username='Sistema (Auto)',
                action='close',
                status='success'
            )
            
            await bot.send_message(
                chat_id=chat_id,
                text="🔒 *Puerta cerrada automáticamente*\n\nLa puerta se ha cerrado después de 10 segundos.",
                parse_mode='Markdown'
            )
    
    def _is_authorized(self, user_id: int) -> bool:
        """Verifica si el usuario está autorizado"""
        if not ALLOWED_USERS or ALLOWED_USERS[0] == '':
            return True  # Si no hay lista, permite todos (desarrollo)
        return str(user_id) in ALLOWED_USERS
    
    def _is_logged_in(self, user_id: int) -> bool:
        """Verifica si el usuario está logueado"""
        return user_id in self.logged_users


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores globales"""
    logger.error(f"Error: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ha ocurrido un error. Por favor, intenta nuevamente."
        )


def main():
    """Función principal"""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado")
        return
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Crear instancia del bot
    bot = SlidingDoorBot()
    
    # Handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("login", bot.login))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_credentials))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot iniciado correctamente")
    logger.info(f"🔐 Credenciales de login configuradas: Usuario='{LOGIN_USERNAME}'")
    
    # Iniciar bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()