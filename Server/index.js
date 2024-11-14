let configData;
let map;
let markers = {};  // To store markers for each vehicle by their client_id
let pathCoordinates = {};  // To store the path coordinates for each vehicle
let pathPolylines = {};  // To store the polyline for each vehicle
let reconnectInterval = 1000;  // Initial reconnection interval (1 second)
let socket;
let reconnectAttempts = 0;  // Counter for reconnection attempts
const MAX_ATTEMPTS = 5;  // Maximum number of reconnection attempts

// Function to load configuration from config.json file
function loadConfig() {
    return fetch('config.json')
        .then(response => response.json())  // Parse the JSON response
        .then(config => {
            configData = config;  // Store the config data
            document.title = configData.TITLE;  // Set the document title from config
            const script = document.createElement('script');  // Create a new script element
            script.src = `https://maps.googleapis.com/maps/api/js?key=${configData.apiKey}&callback=initMap`;  // Google Maps API URL with API key
            script.async = true;  // Load the script asynchronously
            script.defer = true;  // Defer execution of the script until HTML parsing is complete
            document.head.appendChild(script);  // Append the script to the document head
        })
        .catch(error => console.error("Error loading config.json:", error));  // Handle errors
}

// Function to initialize the map
function initMap() {
    map = new google.maps.Map(document.getElementById('map'), {
        zoom: 15,  // Set initial zoom level
        center: { lat: 10.9878, lng: -74.7889 }  // Set initial map center (Barranquilla coordinates)
    });

    initializeWebSocket();  // Call the function to initialize WebSocket connection
}

// Function to initialize WebSocket connection
function initializeWebSocket() {
    if (reconnectAttempts >= MAX_ATTEMPTS) {
        console.log("Maximum reconnect attempts reached");
        return;  // Stop if the maximum reconnect attempts are reached
    }

    socket = new WebSocket(`ws://${configData.AWS_IP}:20000`);  // Open WebSocket connection to the server

    socket.onopen = function () {
        console.log("Connected to WebSocket");
        reconnectInterval = 1000;  // Reset reconnection interval
        reconnectAttempts = 0;  // Reset reconnect attempts counter

        // Fetch the last known locations of cars
        fetch(`http://${configData.AWS_IP}:50000/last_location`)
            .then(response => response.json())
            .then(data => {
                let cars = Array.isArray(data) ? data : [data];  // Handle if data is an array or a single object

                cars.forEach(car => {
                    let clientId = car.client_id;
                    let alias = car.alias;
                    let lastLatLng = new google.maps.LatLng(parseFloat(car.latitud), parseFloat(car.longitud));

                    if (!markers[clientId]) {
                        // Create a marker for each vehicle if it doesn't already exist
                        markers[clientId] = new google.maps.Marker({
                            position: lastLatLng,
                            map: map,
                            icon: {
                                url: "http://geotaxi.ddns.net/icon/taxi.png",
                                scaledSize: new google.maps.Size(25, 25),  // Scale the icon size
                                origin: new google.maps.Point(0, 0),
                                anchor: new google.maps.Point(15, 15)  // Anchor the icon in the center
                            }
                        });

                        pathCoordinates[clientId] = [lastLatLng];  // Initialize the path coordinates for the vehicle
                        pathPolylines[clientId] = new google.maps.Polyline({
                            path: pathCoordinates[clientId],
                            geodesic: true,
                            strokeColor: '#FF0000',  // Red color for the path
                            strokeOpacity: 1.0,
                            strokeWeight: 2,  // Path thickness
                            map: map
                        });

                        // Info window for the vehicle
                        markers[clientId].infoWindow = new google.maps.InfoWindow();
                        markers[clientId].infoWindow.setContent(`
                            <div>
                                <strong>ID:</strong> ${alias}<br>
                            </div>
                        `);

                        markers[clientId].addListener('click', () => {
                            markers[clientId].infoWindow.open(map, markers[clientId]);
                        });
                    } else {
                        markers[clientId].setPosition(lastLatLng);  // Update the marker position if it already exists
                    }

                    map.setCenter(lastLatLng);  // Center the map to the last location of the car
                });
            })
            .catch(error => console.error("Error fetching last location:", error));  // Handle fetch errors
    };

    // Function to handle incoming messages from the WebSocket
    socket.onmessage = function (event) {
        console.log("Message received from WebSocket:", event.data);
        let data = JSON.parse(event.data);  // Parse incoming data
        let alias = data.alias;

        if (!data.client_id) {
            console.error("Message without client_id, cannot process.");
            return;  // Ignore messages without a client_id
        }

        let clientId = data.client_id;
        let latLng = new google.maps.LatLng(parseFloat(data.latitud), parseFloat(data.longitud));  // Convert latitude and longitude to LatLng object

        // Add the new position to the path coordinates
        if (!pathCoordinates[clientId]) {
            pathCoordinates[clientId] = [];
        }
        pathCoordinates[clientId].push(latLng);

        // Create a new marker if it doesn't exist
        if (!markers[clientId]) {
            markers[clientId] = new google.maps.Marker({
                position: latLng,
                map: map,
                icon: {
                    url: "http://geotaxi.ddns.net/icon/taxi.png",
                    scaledSize: new google.maps.Size(25, 25),
                    origin: new google.maps.Point(0, 0),
                    anchor: new google.maps.Point(15, 15)
                }
            });

            pathPolylines[clientId] = new google.maps.Polyline({
                path: pathCoordinates[clientId],
                geodesic: true,
                strokeColor: '#FF0000',
                strokeOpacity: 1.0,
                strokeWeight: 2,
                map: map
            });

            markers[clientId].infoWindow = new google.maps.InfoWindow();
            markers[clientId].addListener('click', () => {
                markers[clientId].infoWindow.open(map, markers[clientId]);
            });
        } else {
            markers[clientId].setPosition(latLng);  // Update the marker position
            pathPolylines[clientId].setPath(pathCoordinates[clientId]);  // Update the polyline path
        }

        // Update the info window with the latest data
        markers[clientId].infoWindow.setContent(`
            <div>
                <strong>ID:</strong> ${alias}<br>
                <strong>Speed:</strong> ${data.velocidad} km/h<br>
                <strong>RPM:</strong> ${data.rpm}<br>
                <strong>Fuel:</strong> ${data.fuel}%
            </div>
        `);
    };

    socket.onerror = function () {
        console.error("WebSocket error");
    };

    socket.onclose = function () {
        console.log("WebSocket closed");
        reconnectAttempts++;  // Increment the reconnect attempts
        console.log(`Reconnect attempt: ${reconnectAttempts}`);
        if (reconnectAttempts < MAX_ATTEMPTS) {
            setTimeout(initializeWebSocket, reconnectInterval);  // Try to reconnect after a delay
            reconnectInterval = Math.min(reconnectInterval * 2, 60000);  // Exponential backoff with a maximum interval of 60 seconds
        } else {
            console.log("Failed to reconnect after several attempts.");
        }
    };
}

loadConfig();  // Load configuration and initialize the map
