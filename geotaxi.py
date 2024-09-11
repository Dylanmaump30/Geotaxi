import socket
import threading
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import re
import json
from websocket_server import WebsocketServer

last_saved_time = None
clients = []

def create_mysql_connection():  
    """Establece una conexión a MySQL."""
    try:
        connection = mysql.connector.connect(
            host='ENDPOINT_RDS',
            user='USER_RDS',
            password='PASSWORD_RDS',
            database='geotaxi_db'
        )
        if connection.is_connected():
            print("Conectado a MySQL")
            return connection
    except Error as e:
        print(f"Error al conectar a MySQL: {e}")
    return None

def handle_tcp_connection():
    """Maneja conexiones TCP y guarda ubicaciones en la base de datos."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        tcp_socket.bind(("", 16000)) 
        tcp_socket.listen()
        print("Servidor TCP escuchando en el puerto 16000")

        while True:
            conn, addr = tcp_socket.accept()  
            print(f"Conectado por {addr}")
            threading.Thread(target=handle_client, args=(conn,)).start() 

def handle_client(conn):
    """Maneja la conexión de un cliente."""
    with conn:
        while True:
            data = conn.recv(1024).decode().strip()
            if not data:  
                break
            print(f"Datos recibidos: '{data}'")  

            match = re.match(r'Latitude:\s*(-?\d+\.\d+)\s+Longitude:\s*(-?\d+\.\d+)\s+Timestamp:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', data)
            
            if match:
                latitud, longitud, fecha, hora = match.groups()
                save_location(latitud, longitud, fecha, hora)
                notify_clients(latitud, longitud, fecha, hora)
                conn.sendall(b"Datos recibidos y guardados.")  
            else:
                print("Datos recibidos en formato incorrecto.")
                conn.sendall(b"Formato de datos incorrecto.")

def save_location(latitud, longitud, fecha, hora):
    """Guarda la ubicación recibida en la base de datos cada 10 segundos."""
    global last_saved_time  

    print(f"Guardando ubicación: latitud={latitud}, longitud={longitud}, fecha={fecha}, hora={hora}")

    current_time = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M:%S")

    if last_saved_time is None or (current_time - last_saved_time) >= timedelta(seconds=10):
        connection = create_mysql_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM ubicaciones
                    WHERE latitud = %s AND longitud = %s AND fecha = %s AND hora = %s
                ''', (latitud, longitud, fecha, hora))
                if cursor.fetchone()[0] > 0:
                    print("Ubicación ya existe en la base de datos.")
                    return

                cursor.execute('''
                    INSERT INTO ubicaciones (latitud, longitud, fecha, hora)
                    VALUES (%s, %s, %s, %s)
                ''', (latitud, longitud, fecha, hora))
                connection.commit()

                last_saved_time = current_time
                print("Ubicación guardada en la base de datos.")
            except Error as e:
                print(f"Error al guardar la ubicación en la base de datos: {e}")
            finally:
                cursor.close()
                connection.close()
                print("Conexión a MySQL cerrada después de guardar la ubicación.")
    else:
        print(f"Ubicación recibida dentro de los últimos 10 segundos. No se guarda.")

def notify_clients(latitud, longitud, fecha, hora):
    """Notifica a los clientes conectados via WebSocket."""
    for client in clients:
        server.send_message(client, json.dumps({
            'latitud': latitud,
            'longitud': longitud,
            'fecha': fecha,
            'hora': hora
        }))

def start_websocket():
    """Inicia el servidor WebSocket."""
    global server
    server = WebsocketServer(host='0.0.0.0', port=20000)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    print("Servidor WebSocket corriendo en el puerto 8000")
    server.run_forever()

def new_client(client, server):
    """Agrega nuevo cliente a la lista."""
    clients.append(client)
    print("Nuevo cliente conectado y agregado a la lista.")

def client_left(client, server):
    """Elimina el cliente de la lista."""
    clients.remove(client)
    print("Cliente desconectado y eliminado de la lista.")

def message_received(client, server, message):
    """Procesa mensajes recibidos (si aplica)."""
    pass

if __name__ == "__main__":
    tcp_thread = threading.Thread(target=handle_tcp_connection, daemon=True)
    ws_thread = threading.Thread(target=start_websocket, daemon=True)

    tcp_thread.start()
    ws_thread.start()

    tcp_thread.join()
    ws_thread.join()