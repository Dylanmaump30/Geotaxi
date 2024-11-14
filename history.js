// Variables for configuration and map elements
let configData;
let map, pathPolyline;
let pathCoordinates = [];
let movingMarker;
let currentStep = 0;
let totalSteps = 0;
const iconUrl = 'http://geotaxi.ddns.net/icon/titleicon3.png';
let aliasPolylines = {};  // Stores polylines for each alias
let aliasMarkers = {};    // Stores markers for each alias

// Function to generate a color based on alias name
function getColorForAlias(alias) {
    let hash = 0;
    for (let i = 0; i < alias.length; i++) {
        hash = (hash << 5) - hash + alias.charCodeAt(i);
        hash = hash & hash;
    }
    const colors = ['#FF0000', '#0000FF', '#00FF00', '#00FFFF'];
    const index = Math.abs(hash) % colors.length;
    return colors[index];
}

// Function to load configuration from config.json file
function loadConfig() {
    return fetch('config.json')
        .then(response => response.json())
        .then(config => {
            configData = config;
            document.getElementById('page-title').innerText = configData.TITLE;
            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${configData.apiKey}&libraries=places&callback=initMap`;
            script.defer = true;
            document.head.appendChild(script);
        })
        .catch(error => console.error("Error loading config.json:", error));
}

// Initialize the map and main moving marker
function initMap() {
    const barranquilla = { lat: 10.9878, lng: -74.7889 };
    map = new google.maps.Map(document.getElementById('map'), {
        zoom: 15,
        center: barranquilla,
        scrollwheel: true
    });

    movingMarker = new google.maps.Marker({
        map: map,
        icon: {
            url: 'http://geotaxi.ddns.net/icon/taxi.png',
            scaledSize: new google.maps.Size(20, 20)
        }
    });
}

// Load the list of aliases from the server
function loadAliases() {
    fetch(`http://${configData.AWS_IP}:60000/get-aliases`, {
        method: 'GET'
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Server response error');
            }
            return response.json();
        })
        .then(aliases => {
            const aliasSelector = document.getElementById('alias-selector');
            if (Array.isArray(aliases)) {
                aliasSelector.innerHTML = `
                    <option value="">Select ID</option>
                    <option value="todos">All</option>`;

                aliases.forEach(alias => {
                    const option = document.createElement('option');
                    option.value = alias;
                    option.textContent = alias;
                    aliasSelector.appendChild(option);
                });
            } else {
                console.error("Invalid alias array.");
            }
        })
        .catch(error => {
            console.error("Error loading aliases:", error);
        });
}

// Group data by alias
function groupByAlias(data) {
    return data.reduce((acc, loc) => {
        if (!acc[loc.alias]) {
            acc[loc.alias] = [];
        }
        acc[loc.alias].push({
            latitud: loc.latitud,
            longitud: loc.longitud,
            fecha: loc.fecha,
            hora: loc.hora,
            velocidad: loc.velocidad,
            rpm: loc.rpm,
            combustible: loc.combustible
        });
        return acc;
    }, {});
}

// Load history based on selected alias and date range
function loadHistory() {
    const startDate = document.getElementById('start-datetime').value;
    const endDate = document.getElementById('end-datetime').value;
    const alias = document.getElementById('alias-selector').value;

    if (!alias) {
        alert("Please select an ID.");
        return;
    }

    if (startDate && endDate) {
        const startDateTime = new Date(startDate);
        const endDateTime = new Date(endDate);

        if (endDateTime <= startDateTime) {
            alert("End date and time must be after start date and time.");
            return;
        }

        const requestBody = {
            start: startDate,
            end: endDate,
            alias: alias === "todos" ? null : alias
        };

        fetch(`http://${configData.AWS_IP}:60000/location-history`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error("No locations found for the specified time range");
                }
                return response.json();
            })
            .then(data => {
                if (Array.isArray(data)) {
                    clearPolylines();
                    clearMarkers();

                    const aliasGroups = groupByAlias(data);
                    let globalBounds = new google.maps.LatLngBounds();
                    for (const alias in aliasGroups) {
                        const aliasData = aliasGroups[alias];
                        drawPolylineForAlias(alias, aliasData);

                        aliasData.forEach(loc => {
                            globalBounds.extend(new google.maps.LatLng(loc.latitud, loc.longitud));
                        });
                    }

                    pathCoordinates = data.map(loc => ({
                        latitud: loc.latitud,
                        longitud: loc.longitud,
                        fecha: loc.fecha,
                        hora: loc.hora,
                        velocidad: loc.velocidad,
                        rpm: loc.rpm,
                        combustible: loc.combustible,
                        alias: loc.alias
                    }));
                    totalSteps = pathCoordinates.length;

                    movingMarker.setPosition(new google.maps.LatLng(pathCoordinates[0].latitud, pathCoordinates[0].longitud));
                    map.setCenter(movingMarker.getPosition());

                    addMarkerClickListener();
                    updateSlider();
                    const alias = pathCoordinates[0].alias || "Unknown";
                    showPopup(pathCoordinates[0].fecha, pathCoordinates[0].hora,
                        pathCoordinates[0].velocidad, pathCoordinates[0].rpm,
                        pathCoordinates[0].combustible, alias);

                    map.fitBounds(globalBounds);
                } else {
                    alert(data.message || "No locations found for the specified date range.");
                }
            })
            .catch(error => {
                console.error("Error fetching location history:", error);
                alert("Error querying location history: " + error.message);
            });
    } else {
        alert("Please select valid dates and times.");
    }
}

// Draw polyline for each alias
function drawPolylineForAlias(alias, aliasData) {
    const color = getColorForAlias(alias);

    const polyline = new google.maps.Polyline({
        path: aliasData.map(loc => new google.maps.LatLng(loc.latitud, loc.longitud)),
        strokeColor: color,
        strokeOpacity: 0.8,
        strokeWeight: 2,
        map: map
    });

    aliasPolylines[alias] = polyline;

    if (aliasData.length > 0) {
        addAliasMarkers(alias, aliasData);
    }
}

// Update slider for path navigation
function updateSlider() {
    const slider = document.getElementById('slider');
    slider.max = 100;
    slider.value = 0;
}

// Limit max date for date selectors
function setMaxDate() {
    const today = new Date();
    const localDate = today.toLocaleDateString('en-CA');
    document.getElementById('start-datetime').setAttribute('max', `${localDate}T23:59`);
    document.getElementById('end-datetime').setAttribute('max', `${localDate}T23:59`);
}

// Add markers for start and end locations of alias path
function addAliasMarkers(alias, aliasData) {
    if (aliasMarkers[alias]) {
        const { startMarker, endMarker } = aliasMarkers[alias];
        if (startMarker) startMarker.setMap(null);
        if (endMarker) endMarker.setMap(null);
    }

    const startLocation = aliasData[0];
    const endLocation = aliasData[aliasData.length - 1];

    const startMarker = new google.maps.Marker({
        position: new google.maps.LatLng(startLocation.latitud, startLocation.longitud),
        map: map,
        title: `Start - ${alias}`,
        icon: {
            url: iconUrl,
            scaledSize: new google.maps.Size(30, 30)
        }
    });

    const endMarker = new google.maps.Marker({
        position: new google.maps.LatLng(endLocation.latitud, endLocation.longitud),
        map: map,
        title: `End - ${alias}`,
        icon: {
            url: iconUrl,
            scaledSize: new google.maps.Size(30, 30)
        }
    });

    aliasMarkers[alias] = { startMarker, endMarker };
}

// Clear all polylines on the map
function clearPolylines() {
    for (const alias in aliasPolylines) {
        aliasPolylines[alias].setMap(null);
    }
    aliasPolylines = {};
}

// Clear all markers on the map
function clearMarkers() {
    for (const alias in aliasMarkers) {
        const { startMarker, endMarker } = aliasMarkers[alias];
        if (startMarker) startMarker.setMap(null);
        if (endMarker) endMarker.setMap(null);
    }
    aliasMarkers = {};
}

// Add click listener to moving marker for popup display
function addMarkerClickListener() {
    movingMarker.addListener('click', () => {
        const currentData = pathCoordinates[currentStep];
        const alias = currentData.alias || "Unknown";
        showPopup(currentData.fecha, currentData.hora, currentData.velocidad, currentData.rpm, currentData.combustible, alias);
    });
}

// Display popup with vehicle details
function showPopup(date, time, speed, rpm, fuel, alias) {
    const popup = document.getElementById("popup");
    popup.style.display = "block";
    popup.innerHTML = `
        <p><strong>Date:</strong> ${date}</p>
        <p><strong>Time:</strong> ${time}</p>
        <p><strong>Speed:</strong> ${speed} km/h</p>
        <p><strong>RPM:</strong> ${rpm}</p>
        <p><strong>Fuel:</strong> ${fuel}%</p>
        <p><strong>Alias:</strong> ${alias}</p>`;
}

// Load configuration and aliases when page is loaded
document.addEventListener('DOMContentLoaded', () => {
    loadConfig().then(() => {
        loadAliases();
        setMaxDate();
    });
});
