from flask import Flask, jsonify, request
import mysql.connector
from datetime import datetime, timedelta, time
from flask_cors import CORS
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Initialize the Flask application
app = Flask(__name__)

# Enable CORS for the '/last_location' route, allowing requests from any origin
CORS(app, resources={r"/last_location": {"origins": "*"}})

# Database configuration using environment variables for sensitive data
db_config = {
    'host': os.getenv('DB_HOST'),  # Database host
    'user': os.getenv('DB_USER'),  # Database username
    'password': os.getenv('DB_PASSWORD'),  # Database password
    'database': os.getenv('DB_NAME')  # Database name
}

# Define a route to retrieve the last location of each client
@app.route('/last_location', methods=['GET'])
def get_last_location():
    try:
        # Establish a connection to the MySQL database using the configuration
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)  # Enable dictionary-based results for easy key access

        # Query to get the last known location (based on the latest date and time) for each client
        cursor.execute('''
            SELECT client_id, latitud, longitud, fecha, hora, alias
            FROM ubicaciones
            WHERE (client_id, fecha, hora) IN (
                SELECT client_id, MAX(fecha), MAX(hora)
                FROM ubicaciones
                GROUP BY client_id
            )
        ''')

        # Fetch all results from the query
        last_locations = cursor.fetchall()

        # Format the 'fecha' and 'hora' fields to ensure they are in a readable format
        for location in last_locations:
            # Format the 'fecha' as YYYY-MM-DD
            location['fecha'] = location['fecha'].strftime('%Y-%m-%d')
            # Format 'hora' as HH:MM:SS if it's a datetime object
            location['hora'] = location['hora'].strftime('%H:%M:%S') if isinstance(location['hora'], datetime) else str(location['hora'])

        # Return the formatted results as a JSON response with a 200 OK status
        return jsonify(last_locations), 200

    # Handle MySQL connection errors
    except mysql.connector.Error as e:
        # Return the error as a JSON response with a 500 Internal Server Error status
        return jsonify({"error": str(e)}), 500
    
    # Ensure the database connection is closed, whether the request was successful or not
    finally:
        cursor.close()
        connection.close()

# Run the Flask application on host '0.0.0.0' and port 50000, so it is accessible from any IP
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=50000)
