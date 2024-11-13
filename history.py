from flask import Flask, jsonify, request
import mysql.connector
from datetime import datetime, timedelta, time
from flask_cors import CORS
import os
from dotenv import load_dotenv

# Initialize the Flask application
app = Flask(__name__)

# Enable CORS for the '/location-history' and '/get-aliases' routes, allowing requests from any origin
CORS(app, resources={r"/location-history": {"origins": "*"}, r"/get-aliases": {"origins": "*"}})

# Load environment variables from a .env file (e.g., for database credentials)
load_dotenv()

# Database configuration using environment variables for sensitive information
db_config = {
    'host': os.getenv('DB_HOST'),  # Database host
    'user': os.getenv('DB_USER'),  # Database username
    'password': os.getenv('DB_PASSWORD'),  # Database password
    'database': os.getenv('DB_NAME')  # Database name
}

# Define the route to get the location history based on a time range
@app.route('/location-history', methods=['POST'])
def get_location_history():
    request_data = request.get_json()  # Parse the incoming JSON request
    start_datetime_str = request_data['start']  # Start datetime string from request
    end_datetime_str = request_data['end']  # End datetime string from request
    alias = request_data.get('alias', None)  # Optionally get the alias from request

    connection = None
    cursor = None

    try:
        # Convert the start and end datetime strings into datetime objects
        start_datetime = datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
        end_datetime = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M')

        # Ensure the end datetime is not earlier than the start datetime
        if end_datetime < start_datetime:
            return jsonify({"error": "The end datetime cannot be earlier than the start datetime."}), 400

        # Connect to the database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # Query for locations in the specified time range, optionally filtered by alias
        if alias:
            query = '''SELECT latitud, longitud, fecha, hora, velocidad, rpm, combustible, alias
                       FROM ubicaciones
                       WHERE (fecha > %s OR (fecha = %s AND hora >= %s)) AND
                             (fecha < %s OR (fecha = %s AND hora <= %s)) AND
                             alias = %s'''
            cursor.execute(query, (
                start_datetime.date(), start_datetime.date(), start_datetime.time(),
                end_datetime.date(), end_datetime.date(), end_datetime.time(),
                alias
            ))
        else:
            query = '''SELECT latitud, longitud, fecha, hora, velocidad, rpm, combustible, alias
                       FROM ubicaciones
                       WHERE (fecha > %s OR (fecha = %s AND hora >= %s)) AND
                             (fecha < %s OR (fecha = %s AND hora <= %s))'''
            cursor.execute(query, (
                start_datetime.date(), start_datetime.date(), start_datetime.time(),
                end_datetime.date(), end_datetime.date(), end_datetime.time()
            ))

        # Fetch all the results
        locations = cursor.fetchall()

        # Format the 'fecha' and 'hora' fields to be human-readable
        for loc in locations:
            loc['fecha'] = loc['fecha'].strftime('%Y-%m-%d')  # Format the date
            if isinstance(loc['hora'], str):
                loc['hora'] = datetime.strptime(loc['hora'], '%H:%M:%S').time()  # Convert string to time object
            elif isinstance(loc['hora'], timedelta):
                total_seconds = int(loc['hora'].total_seconds())  # Convert timedelta to total seconds
                loc['hora'] = (datetime(1, 1, 1) + timedelta(seconds=total_seconds)).time()  # Convert seconds to time
            if isinstance(loc['hora'], time):
                loc['hora'] = loc['hora'].strftime('%H:%M:%S')  # Format time as HH:MM:SS

        # Return the locations as a JSON response, or a message if no locations are found
        if locations:
            return jsonify(locations), 200
        else:
            return jsonify({"message": "No locations found for the specified time range."}), 404
    except mysql.connector.Error as e:
        # Handle MySQL errors and return a 500 status with the error message
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        # Handle general errors
        return jsonify({"error": str(e)}), 500
    finally:
        # Ensure that the database connection and cursor are closed
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# Define the route to get all available aliases
@app.route('/get-aliases', methods=['GET'])
def get_aliases():
    connection = None
    cursor = None
    try:
        # Connect to the database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # Query to fetch all distinct aliases from the aliases table
        cursor.execute("SELECT DISTINCT alias FROM aliases")
        aliases = cursor.fetchall()
        
        # Return the list of aliases as a JSON response
        return jsonify([alias['alias'] for alias in aliases]), 200
    except mysql.connector.Error as e:
        # Handle MySQL errors and return a 500 status with the error message
        return jsonify({"error": str(e)}), 500
    finally:
        # Ensure that the database connection and cursor are closed
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# Run the Flask application on host '0.0.0.0' and port 60000, enabling debugging
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=60000, debug=True)