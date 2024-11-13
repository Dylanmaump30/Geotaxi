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
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Global variables
last_saved_timestamp = None
clients = []
location_cache = []
processed_messages = set()  # Set to store hashes of processed messages
backlog_size = 50  # Backlog size for pending connections
tcp_socket_timeout = 20  # Timeout for accepting connections on the main socket
client_socket_timeout = 15  # Timeout for read/write operations
save_lock = asyncio.Lock()
alias_cache = {}  # Cache to store generated aliases for client_id

# Create a pool of connections to the MySQL database
connection_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=10,
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

# Configuration for WebSocket Throttling
NOTIFICATION_THRESHOLD = 5  # Send notifications at most every 5 seconds
last_notification_time = time.time()

def hash_message(message):
    """Creates a hash from the message to prevent duplicates."""
    return hashlib.sha256(message.encode()).hexdigest()

def generate_alias(client_id):
    """Generates a unique sequential alias like 'taxi X'."""
    if client_id in alias_cache:
        return alias_cache[client_id]
    
    try:
        connection = connection_pool.get_connection()
        cursor = connection.cursor()

        # Check if the client_id already has an alias registered in the database
        cursor.execute("SELECT alias FROM aliases WHERE client_id = %s", (client_id,))
        result = cursor.fetchone()

        if result:
            alias = result[0]  # Retrieve the existing alias
        else:
            # Count the number of rows to get the next available number
            cursor.execute("SELECT COUNT(*) FROM aliases")
            next_number = cursor.fetchone()[0] + 1
            alias = f"taxi {next_number}"
            
            # Insert the new alias for the client_id into the aliases table
            cursor.execute("INSERT INTO aliases (client_id, alias) VALUES (%s, %s)", (client_id, alias))
            connection.commit()

        alias_cache[client_id] = alias  # Save to cache for future use
    finally:
        cursor.close()
        connection.close()

    return alias

async def handle_tcp_connection():
    """Handles TCP connections and saves locations to the database."""
    global backlog_size, tcp_socket_timeout
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        tcp_socket.settimeout(tcp_socket_timeout)
        tcp_socket.bind(("", 16000))
        tcp_socket.listen(backlog_size)
        print("TCP server listening on port 16000")

        while True:
            try:
                conn, addr = await asyncio.to_thread(tcp_socket.accept)
                print(f"Connected by {addr}")
                asyncio.create_task(handle_client(conn))
            except socket.timeout:
                print("Timeout expired, retrying...")

async def handle_client(conn):
    """Handles a TCP client connection."""
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
                    print(f"Received data: '{message}'")
                    # Update the regex to match the expected format
                    match = re.match(
                        r'ID:\s*(\w+)\s+Latitude:\s*(-?\d+\.\d+)\s+Longitude:\s*(-?\d+\.\d+)\s+Timestamp:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+Speed:\s*(\d+(?:\.\d+)?)\s+RPM:\s*(\d+(?:\.\d+)?)\s+Fuel:\s*(\d+(?:\.\d+)?)',
                        message
                    )
                    if match:
                        client_id, latitude, longitude, timestamp, speed, rpm, fuel = match.groups()
                        alias = generate_alias(client_id)
                        date, time_str = timestamp.split()
                        location_cache.append((client_id, alias, latitude, longitude, date, time_str, speed, rpm, fuel))
                        await save_locations_in_batch()
                        
                        # Pass the client_id when calling notify_clients
                        await notify_clients(client_id, alias, latitude, longitude, date, time_str, speed, rpm, fuel)
                        
                        await asyncio.to_thread(conn.sendall, b"Data received and saved.")
                    else:
                        print("Received data in incorrect format.")
                        await asyncio.to_thread(conn.sendall, b"Incorrect data format.")
        except socket.timeout:
            print("TCP connection closed due to timeout.")
        except Exception as e:
            print(f"Error in TCP connection: {e}")

async def save_locations_in_batch():
    """Saves locations to the database in batches."""
    global last_saved_timestamp
    if not location_cache:
        return
    
    current_timestamp = time.time()
    
    # Check if 10 seconds have passed since the last save
    if last_saved_timestamp is None or (current_timestamp - last_saved_timestamp) >= 10:
        async with save_lock:
            try:
                connection = connection_pool.get_connection()
                cursor = connection.cursor()
                cursor.executemany('''INSERT IGNORE INTO ubicaciones (client_id, alias, latitud, longitud, fecha, hora, velocidad, rpm, combustible) 
                                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''', location_cache)
                connection.commit()
                last_saved_timestamp = current_timestamp
                location_cache.clear()
                print(f"Locations saved to the database. Current time: {datetime.fromtimestamp(current_timestamp)}")
            except mysql.connector.Error as e:
                print(f"Error saving to the database: {e}")
            finally:
                cursor.close()
                connection.close()

async def notify_clients(client_id, alias, latitude, longitude, date, time_str, speed, rpm, fuel):
    """Notifies connected WebSocket clients in a throttled manner."""
    global last_notification_time
    current_time = time.time()
    
    if current_time - last_notification_time >= NOTIFICATION_THRESHOLD:
        message = json.dumps({
            'client_id': client_id,
            'alias': alias,
            'latitude': latitude, 
            'longitude': longitude, 
            'date': date, 
            'time': time_str,
            'speed': speed,
            'rpm': rpm,
            'fuel': fuel
        })
        for client in clients:
            await asyncio.to_thread(server.send_message, client, message)
        last_notification_time = current_time
        print("Clients notified.")

def start_websocket():
    """Starts the WebSocket server."""
    global server
    server = WebsocketServer(host='0.0.0.0', port=20000)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    print("WebSocket server running on port 20000")
    server.run_forever()

def new_client(client, server):
    """Adds a new client to the clients list."""
    clients.append(client)
    print("New client connected and added to the list.")

def client_left(client, server):
    """Removes a client from the clients list."""
    clients.remove(client)
    print("Client disconnected and removed from the list.")

def message_received(client, server, message):
    """Processes received messages (if applicable)."""
    pass  # Currently not handling incoming messages from clients

async def main():
    """Main function to run TCP and WebSocket servers concurrently."""
    tcp_task = asyncio.create_task(handle_tcp_connection())
    ws_task = asyncio.to_thread(start_websocket)

    try:
        await asyncio.gather(tcp_task, ws_task)
    except KeyboardInterrupt:
        print("Server stopped by user.")
    finally:
        tcp_task.cancel()
        ws_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
