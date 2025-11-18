import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """Gestiona el almacenamiento de historial de acciones"""
    
    def __init__(self, db_path: str = 'door_history.db'):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Inicializa la base de datos y crea las tablas necesarias"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Tabla de acciones
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        action TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Índice para búsquedas rápidas
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON actions(timestamp DESC)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_user_id 
                    ON actions(user_id)
                ''')
                
                conn.commit()
                logger.info("✅ Base de datos inicializada correctamente")
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error inicializando base de datos: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexiones a la base de datos"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def log_action(
        self,
        user_id: int,
        username: str,
        action: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra una acción en la base de datos
        
        Args:
            user_id: ID del usuario de Telegram
            username: Nombre de usuario
            action: 'open' o 'close'
            status: 'success' o 'error'
            error_message: Mensaje de error si status='error'
        
        Returns:
            bool: True si se guardó correctamente
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO actions (user_id, username, action, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, action, status, error_message))
                conn.commit()
                
                logger.info(
                    f"📝 Acción registrada: {username} - {action} - {status}"
                )
                return True
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error guardando acción: {e}")
            return False
    
    def get_recent_actions(self, limit: int = 10) -> List[Dict]:
        """
        Obtiene las acciones más recientes
        
        Args:
            limit: Número máximo de registros a retornar
        
        Returns:
            Lista de diccionarios con los registros
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        user_id,
                        username,
                        action,
                        status,
                        error_message,
                        datetime(timestamp, 'localtime') as timestamp
                    FROM actions
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error obteniendo historial: {e}")
            return []
    
    def get_user_actions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Obtiene las acciones de un usuario específico"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        action,
                        status,
                        datetime(timestamp, 'localtime') as timestamp
                    FROM actions
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (user_id, limit))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error obteniendo acciones de usuario: {e}")
            return []
    
    def get_statistics(self, days: int = 7) -> Dict:
        """
        Obtiene estadísticas de uso
        
        Args:
            days: Número de días a analizar
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Total de acciones
                cursor.execute('''
                    SELECT COUNT(*) as total
                    FROM actions
                    WHERE timestamp >= datetime('now', '-' || ? || ' days')
                ''', (days,))
                total = cursor.fetchone()['total']
                
                # Acciones exitosas
                cursor.execute('''
                    SELECT COUNT(*) as successful
                    FROM actions
                    WHERE timestamp >= datetime('now', '-' || ? || ' days')
                    AND status = 'success'
                ''', (days,))
                successful = cursor.fetchone()['successful']
                
                # Acciones por tipo
                cursor.execute('''
                    SELECT action, COUNT(*) as count
                    FROM actions
                    WHERE timestamp >= datetime('now', '-' || ? || ' days')
                    GROUP BY action
                ''', (days,))
                actions_by_type = {row['action']: row['count'] for row in cursor.fetchall()}
                
                # Usuarios más activos
                cursor.execute('''
                    SELECT username, COUNT(*) as count
                    FROM actions
                    WHERE timestamp >= datetime('now', '-' || ? || ' days')
                    GROUP BY user_id, username
                    ORDER BY count DESC
                    LIMIT 5
                ''', (days,))
                top_users = [
                    {'username': row['username'], 'count': row['count']}
                    for row in cursor.fetchall()
                ]
                
                return {
                    'total_actions': total,
                    'successful_actions': successful,
                    'error_rate': round((total - successful) / total * 100, 2) if total > 0 else 0,
                    'actions_by_type': actions_by_type,
                    'top_users': top_users
                }
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}
    
    def cleanup_old_records(self, days: int = 90) -> int:
        """
        Elimina registros antiguos
        
        Args:
            days: Eliminar registros más antiguos que X días
        
        Returns:
            Número de registros eliminados
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM actions
                    WHERE timestamp < datetime('now', '-' || ? || ' days')
                ''', (days,))
                deleted = cursor.rowcount
                conn.commit()
                
                logger.info(f"🗑️ Eliminados {deleted} registros antiguos")
                return deleted
                
        except sqlite3.Error as e:
            logger.error(f"❌ Error limpiando registros: {e}")
            return 0


# Funciones de utilidad para consultas comunes
def get_last_action() -> Optional[Dict]:
    """Obtiene la última acción registrada"""
    db = Database()
    actions = db.get_recent_actions(limit=1)
    return actions[0] if actions else None


def get_action_count_today() -> int:
    """Obtiene el número de acciones realizadas hoy"""
    db = Database()
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM actions
                WHERE DATE(timestamp) = DATE('now')
            ''')
            return cursor.fetchone()['count']
    except sqlite3.Error:
        return 0