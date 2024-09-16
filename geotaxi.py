import asyncio
import socket
import hashlib
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import re
import json
import time
from websocket_server import WebsocketServer

# Variables globales
last_saved_timestamp = None
clients = []
location_cache = []
processed_messages = set()  # set para almacenar hashes de mensajes procesados
backlog_size = 50  # Tamaño del backlog para conexiones pendientes
tcp_socket_timeout = 20  # Timeout para aceptar conexiones en el socket principal
client_socket_timeout = 15  # Timeout para operaciones de lectura/escritura
save_lock = asyncio.Lock()

# Crear un pool de conexiones a la base de datos
connection_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=10,
    host='ENDPOINT',
    user='USER',
    password='PASSWORD',
    database='DATABASE'
)

# Configuración del Throttle para WebSocket
NOTIFICATION_THRESHOLD = 5  # Enviar notificaciones cada 5 segundos como máximo
last_notification_time = time.time()

def hash_message(message):
    """Crea un hash a partir del mensaje para evitar duplicados."""
    return hashlib.sha256(message.encode()).hexdigest()

async def handle_tcp_connection():
    """Maneja conexiones TCP y guarda ubicaciones en la base de datos."""
    global backlog_size, tcp_socket_timeout
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        tcp_socket.settimeout(tcp_socket_timeout)
        tcp_socket.bind(("", 16000))
        tcp_socket.listen(backlog_size)
        print("Servidor TCP escuchando en el puerto 16000")

        while True:
            try:
                conn, addr = await asyncio.to_thread(tcp_socket.accept)
                print(f"Conectado por {addr}")
                asyncio.create_task(handle_client(conn))
            except socket.timeout:
                print("Tiempo de espera agotado, reintentando...")

async def handle_client(conn):
    """Maneja la conexión de un cliente TCP."""
    global client_socket_timeout
    with conn:
        conn.settimeout(client_socket_timeout)
        buffer = []
        try:
            while True:
                data = await asyncio.to_thread(conn.recv, 1024)
                if not data:
                    break

                message = data.decode().strip()
                hashed_message = hash_message(message)

                if message and hashed_message not in processed_messages:
                    processed_messages.add(hashed_message)
                    buffer.append(message)
                    print(f"Datos recibidos: '{message}'")
                    
                    match = re.match(r'Latitude:\s*(-?\d+\.\d+)\s+Longitude:\s*(-?\d+\.\d+)\s+Timestamp:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', message)
                    if match:
                        latitud, longitud, fecha, hora = match.groups()
                        location_cache.append((latitud, longitud, fecha, hora))
                        await save_locations_in_batch()
                        await notify_clients(latitud, longitud, fecha, hora)
                        await asyncio.to_thread(conn.sendall, b"Datos recibidos y guardados.")
                    else:
                        print("Datos recibidos en formato incorrecto.")
                        await asyncio.to_thread(conn.sendall, b"Formato de datos incorrecto.")
        except socket.timeout:
            print("Conexión TCP cerrada por timeout.")
        except Exception as e:
            print(f"Error en la conexión TCP: {e}")

async def save_locations_in_batch():
    """Guarda las ubicaciones en la base de datos en lotes."""
    global last_saved_timestamp
    if not location_cache:
        return
    
    current_timestamp = time.time()
    
    # Verificar si han pasado 10 segundos desde el último guardado
    if last_saved_timestamp is None or (current_timestamp - last_saved_timestamp) >= 10:
        async with save_lock:
            try:
                connection = connection_pool.get_connection()
                cursor = connection.cursor()
                cursor.executemany('''INSERT IGNORE INTO ubicaciones (latitud, longitud, fecha, hora) 
                                      VALUES (%s, %s, %s, %s)''', location_cache)
                connection.commit()
                last_saved_timestamp = current_timestamp
                location_cache.clear()
                print(f"Ubicaciones guardadas en la base de datos. Tiempo actual: {datetime.fromtimestamp(current_timestamp)}")
            except mysql.connector.Error as e:
                print(f"Error al guardar en la base de datos: {e}")
            finally:
                cursor.close()
                connection.close()

async def notify_clients(latitud, longitud, fecha, hora):
    """Notifica a los clientes conectados via WebSocket de manera throttled."""
    global last_notification_time
    current_time = time.time()
    
    if current_time - last_notification_time >= NOTIFICATION_THRESHOLD:
        message = json.dumps({'latitud': latitud, 'longitud': longitud, 'fecha': fecha, 'hora': hora})
        for client in clients:
            await asyncio.to_thread(server.send_message, client, message)
        last_notification_time = current_time
        print("Clientes notificados.")

def start_websocket():
    """Inicia el servidor WebSocket."""
    global server
    server = WebsocketServer(host='0.0.0.0', port=20000)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    print("Servidor WebSocket corriendo en el puerto 20000")
    server.run_forever()

def new_client(client, server):
    """Agrega un nuevo cliente a la lista."""
    clients.append(client)
    print("Nuevo cliente conectado y agregado a la lista.")

def client_left(client, server):
    """Elimina un cliente de la lista."""
    clients.remove(client)
    print("Cliente desconectado y eliminado de la lista.")

def message_received(client, server, message):
    """Procesa mensajes recibidos (si aplica)."""
    pass

async def main():
    tcp_task = asyncio.create_task(handle_tcp_connection())
    ws_task = asyncio.to_thread(start_websocket)

    try:
        await asyncio.gather(tcp_task, ws_task)
    except KeyboardInterrupt:
        print("Servidor detenido por el usuario.")
    finally:
        tcp_task.cancel()
        ws_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())

