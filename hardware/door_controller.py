import os
import asyncio
import logging
from typing import Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Configuración
DOOR_TYPE = os.getenv('DOOR_TYPE', 'simulation')  # simulation, gpio, api


class DoorInterface(ABC):
    """Interfaz abstracta para controladores de puertas"""
    
    @abstractmethod
    async def open(self) -> Dict[str, Any]:
        """Abre la puerta"""
        pass
    
    @abstractmethod
    async def close(self) -> Dict[str, Any]:
        """Cierra la puerta"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado de la puerta"""
        pass


class SimulationDoor(DoorInterface):
    """Simulador de puerta para pruebas"""
    
    def __init__(self):
        self.is_open = False
        self.system_ok = True
    
    async def open(self) -> Dict[str, Any]:
        """Simula la apertura de la puerta"""
        logger.info("🚪 Simulando apertura de puerta...")
        await asyncio.sleep(2)  # Simula el tiempo de apertura
        
        self.is_open = True
        logger.info("✅ Puerta abierta (simulación)")
        
        return {
            'success': True,
            'message': 'Puerta abierta correctamente',
            'timestamp': asyncio.get_event_loop().time()
        }
    
    async def close(self) -> Dict[str, Any]:
        """Simula el cierre de la puerta"""
        logger.info("🔒 Simulando cierre de puerta...")
        await asyncio.sleep(2)  # Simula el tiempo de cierre
        
        self.is_open = False
        logger.info("✅ Puerta cerrada (simulación)")
        
        return {
            'success': True,
            'message': 'Puerta cerrada correctamente',
            'timestamp': asyncio.get_event_loop().time()
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """Retorna el estado simulado"""
        return {
            'door_open': self.is_open,
            'system_ok': self.system_ok
        }


class GPIODoor(DoorInterface):
    """Control de puerta mediante GPIO (Raspberry Pi)"""
    
    def __init__(self):
        self.is_open = False
        self.relay_pin_open = int(os.getenv('GPIO_PIN_OPEN', '17'))
        self.relay_pin_close = int(os.getenv('GPIO_PIN_CLOSE', '18'))
        self.sensor_pin = int(os.getenv('GPIO_PIN_SENSOR', '27'))
        
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self._setup_gpio()
            self.system_ok = True
            logger.info("✅ GPIO inicializado correctamente")
        except ImportError:
            logger.warning("⚠️ RPi.GPIO no disponible. Usando modo simulación.")
            self.GPIO = None
            self.system_ok = False
        except Exception as e:
            logger.error(f"❌ Error inicializando GPIO: {e}")
            self.GPIO = None
            self.system_ok = False
    
    def _setup_gpio(self):
        """Configura los pines GPIO"""
        if not self.GPIO:
            return
        
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        
        # Configurar pines de relés (salida)
        self.GPIO.setup(self.relay_pin_open, self.GPIO.OUT)
        self.GPIO.setup(self.relay_pin_close, self.GPIO.OUT)
        
        # Configurar pin de sensor (entrada)
        self.GPIO.setup(self.sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
        
        # Inicializar relés en OFF
        self.GPIO.output(self.relay_pin_open, self.GPIO.LOW)
        self.GPIO.output(self.relay_pin_close, self.GPIO.LOW)
    
    async def open(self) -> Dict[str, Any]:
        """Abre la puerta activando el relé"""
        if not self.GPIO:
            return {
                'success': False,
                'error': 'GPIO no disponible'
            }
        
        try:
            logger.info("🚪 Abriendo puerta vía GPIO...")
            
            # Activar relé de apertura
            self.GPIO.output(self.relay_pin_open, self.GPIO.HIGH)
            await asyncio.sleep(1)  # Mantener señal por 1 segundo
            self.GPIO.output(self.relay_pin_open, self.GPIO.LOW)
            
            # Esperar a que la puerta se abra completamente
            await asyncio.sleep(3)
            
            self.is_open = True
            logger.info("✅ Puerta abierta vía GPIO")
            
            return {
                'success': True,
                'message': 'Puerta abierta correctamente',
                'timestamp': asyncio.get_event_loop().time()
            }
            
        except Exception as e:
            logger.error(f"❌ Error abriendo puerta: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def close(self) -> Dict[str, Any]:
        """Cierra la puerta activando el relé"""
        if not self.GPIO:
            return {
                'success': False,
                'error': 'GPIO no disponible'
            }
        
        try:
            logger.info("🔒 Cerrando puerta vía GPIO...")
            
            # Activar relé de cierre
            self.GPIO.output(self.relay_pin_close, self.GPIO.HIGH)
            await asyncio.sleep(1)
            self.GPIO.output(self.relay_pin_close, self.GPIO.LOW)
            
            # Esperar a que la puerta se cierre
            await asyncio.sleep(3)
            
            self.is_open = False
            logger.info("✅ Puerta cerrada vía GPIO")
            
            return {
                'success': True,
                'message': 'Puerta cerrada correctamente',
                'timestamp': asyncio.get_event_loop().time()
            }
            
        except Exception as e:
            logger.error(f"❌ Error cerrando puerta: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_status(self) -> Dict[str, Any]:
        """Lee el estado del sensor de puerta"""
        if not self.GPIO:
            return {
                'door_open': self.is_open,
                'system_ok': False
            }
        
        try:
            # Leer sensor (LOW = abierta, HIGH = cerrada)
            sensor_state = self.GPIO.input(self.sensor_pin)
            self.is_open = (sensor_state == self.GPIO.LOW)
            
            return {
                'door_open': self.is_open,
                'system_ok': self.system_ok
            }
        except Exception as e:
            logger.error(f"Error leyendo sensor: {e}")
            return {
                'door_open': self.is_open,
                'system_ok': False
            }
    
    def cleanup(self):
        """Limpia los recursos GPIO"""
        if self.GPIO:
            self.GPIO.cleanup()


class APIDoor(DoorInterface):
    """Control de puerta mediante API REST externa"""
    
    def __init__(self):
        self.is_open = False
        self.api_url = os.getenv('DOOR_API_URL', 'http://localhost:8080')
        self.api_key = os.getenv('DOOR_API_KEY', '')
        self.system_ok = True
    
    async def open(self) -> Dict[str, Any]:
        """Abre la puerta mediante API"""
        import aiohttp
        
        try:
            logger.info("🚪 Abriendo puerta vía API...")
            
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.api_key}'}
                async with session.post(
                    f'{self.api_url}/api/door/open',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.is_open = True
                        logger.info("✅ Puerta abierta vía API")
                        return {
                            'success': True,
                            'message': 'Puerta abierta correctamente',
                            'data': data
                        }
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Error en API: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def close(self) -> Dict[str, Any]:
        """Cierra la puerta mediante API"""
        import aiohttp
        
        try:
            logger.info("🔒 Cerrando puerta vía API...")
            
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.api_key}'}
                async with session.post(
                    f'{self.api_url}/api/door/close',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.is_open = False
                        logger.info("✅ Puerta cerrada vía API")
                        return {
                            'success': True,
                            'message': 'Puerta cerrada correctamente',
                            'data': data
                        }
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Error en API: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado mediante API"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.api_key}'}
                async with session.get(
                    f'{self.api_url}/api/door/status',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.is_open = data.get('is_open', False)
                        return {
                            'door_open': self.is_open,
                            'system_ok': True
                        }
                    else:
                        raise Exception(f"API error: {response.status}")
        except Exception as e:
            logger.error(f"Error obteniendo estado: {e}")
            return {
                'door_open': self.is_open,
                'system_ok': False
            }


class DoorController:
    """Controlador principal que gestiona la interfaz de puerta"""
    
    def __init__(self):
        self.door = self._create_door_interface()
        logger.info(f"💡 Usando controlador: {DOOR_TYPE}")
    
    def _create_door_interface(self) -> DoorInterface:
        """Factory para crear la interfaz apropiada"""
        if DOOR_TYPE == 'gpio':
            return GPIODoor()
        elif DOOR_TYPE == 'api':
            return APIDoor()
        else:
            return SimulationDoor()
    
    async def open_door(self) -> Dict[str, Any]:
        """Abre la puerta"""
        return await self.door.open()
    
    async def close_door(self) -> Dict[str, Any]:
        """Cierra la puerta"""
        return await self.door.close()
    
    async def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado de la puerta"""
        return await self.door.get_status()