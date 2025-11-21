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

class SlidingDoorBot:
    def __init__(self):
        self.door_controller = DoorController()
        self.db = Database()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - Mensaje de bienvenida"""
        user = update.effective_user
        
        if not self._is_authorized(user.id):
            await update.message.reply_text(
                "❌ No estás autorizado para usar este bot.\n"
                f"Tu ID: {user.id}"
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("🚪 Abrir Puerta", callback_data="open_door"),
                InlineKeyboardButton("🔒 Cerrar Puerta", callback_data="close_door")
            ],
            [
                InlineKeyboardButton("📊 Estado", callback_data="status"),
                InlineKeyboardButton("📜 Historial", callback_data="history")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 ¡Hola {user.first_name}!\n\n"
            "🏠 *Sistema de Control de Puertas*\n\n"
            "Selecciona una opción:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja las pulsaciones de botones"""
        query = update.callback_query
        user = query.from_user
        
        if not self._is_authorized(user.id):
            await query.answer("❌ No autorizado", show_alert=True)
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
        elif action == "back_menu":
            await self._show_main_menu(query)
    
    async def _handle_open_door(self, query, user):
        """Procesa la apertura de puerta"""
        try:
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
        records = self.db.get_recent_actions(limit=10)
        
        if not records:
            message = "📜 *Historial*\n\nNo hay registros aún."
        else:
            message = "📜 *Historial de Acciones*\n\n"
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
    
    async def _show_main_menu(self, query):
        """Muestra el menú principal"""
        keyboard = [
            [
                InlineKeyboardButton("🚪 Abrir Puerta", callback_data="open_door"),
                InlineKeyboardButton("🔒 Cerrar Puerta", callback_data="close_door")
            ],
            [
                InlineKeyboardButton("📊 Estado", callback_data="status"),
                InlineKeyboardButton("📜 Registro_BD", callback_data="history")
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
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot iniciado correctamente")
    
    # Iniciar bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()