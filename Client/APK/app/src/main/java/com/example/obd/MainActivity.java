package com.example.obd;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.location.Location;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

public class MainActivity extends AppCompatActivity {

    private TextView textView, speedTextView, rpmTextView, fuelLevelTextView;
    private Button btnEnviar;
    private FusedLocationProviderClient fusedLocationProviderClient;
    private LocationCallback locationCallback;
    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSocket bluetoothSocket;
    private OutputStream outputStream;
    private InputStream inputStream;
    private String client_id;
    private Spinner modeSpinner;
    private String selectedMode = "GPS y OBD"; // Valor inicial

    private static final String TAG = "OBD2App";
    private static final int REQUEST_BLUETOOTH_PERMISSION = 1;

    private final String[] ipAWS = {
            "34.207.103.193",
            "18.219.246.163",
            "18.119.0.51"
    };
    private final int puertoTCP = 16000;

    private Handler handler;
    private int vehicleSpeed = 0;
    private int rpm = 0;
    private int fuelLevel = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        client_id = Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
        btnEnviar = findViewById(R.id.enviar);
        textView = findViewById(R.id.Coordenadas);
        speedTextView = findViewById(R.id.textViewSpeed);
        rpmTextView = findViewById(R.id.textViewRPM);
        fuelLevelTextView = findViewById(R.id.textViewFuelLevel);

        // Configuración del Spinner
        modeSpinner = findViewById(R.id.vehicleModeSpinner);
        ArrayAdapter<CharSequence> adapter = ArrayAdapter.createFromResource(this,
                R.array.vehicle_modes, android.R.layout.simple_spinner_item);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        modeSpinner.setAdapter(adapter);

        modeSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                selectedMode = (String) parent.getItemAtPosition(position);
                // Detener las actualizaciones al cambiar de modo
                stopLocationUpdates();
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {}
        });

        // Solicitar permisos necesarios
        ActivityCompat.requestPermissions(this, new String[]{
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN,
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT
        }, REQUEST_BLUETOOTH_PERMISSION);

        fusedLocationProviderClient = LocationServices.getFusedLocationProviderClient(this);
        bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();

        handler = new Handler();

        btnEnviar.setOnClickListener(view -> {
            // Comienza las actualizaciones en función del modo seleccionado
            if (selectedMode.equals("GPS y OBD")) {
                initializeBluetooth();
            }
            startLocationUpdates();
        });
    }

    private void initializeBluetooth() {
        if (bluetoothAdapter == null) {
            Toast.makeText(this, "Bluetooth no disponible", Toast.LENGTH_SHORT).show();
            return;
        }

        BluetoothDevice elmDevice = findPairedDevice("OBDII");
        if (elmDevice != null) {
            connectToOBD2Device(elmDevice);
        } else {
            Toast.makeText(this, "Dispositivo OBD-II no encontrado", Toast.LENGTH_SHORT).show();
        }
    }

    @SuppressLint("MissingPermission")
    private BluetoothDevice findPairedDevice(String deviceName) {
        Set<BluetoothDevice> pairedDevices = bluetoothAdapter.getBondedDevices();
        for (BluetoothDevice device : pairedDevices) {
            if (device.getName().equals(deviceName)) return device;
        }
        return null;
    }

    @SuppressLint("MissingPermission")
    private void connectToOBD2Device(BluetoothDevice device) {
        UUID uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
        try {
            bluetoothSocket = device.createRfcommSocketToServiceRecord(uuid);
            bluetoothSocket.connect();

            outputStream = bluetoothSocket.getOutputStream();
            inputStream = bluetoothSocket.getInputStream();

            startOBD2Communication();

        } catch (IOException e) {
            Log.e(TAG, "Error al conectar con OBD-II: " + e.getMessage());
        }
    }

    private void startOBD2Communication() {
        final Handler handler = new Handler(Looper.getMainLooper());
        final int delay = 1000;

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                try {
                    if (selectedMode.equals("GPS y OBD")) {
                        sendOBD2Command("010D");
                        String speedResponse = readOBD2Response();
                        vehicleSpeed = parseSpeed(speedResponse);

                        Thread.sleep(500);

                        sendOBD2Command("010C");
                        String rpmResponse = readOBD2Response();
                        rpm = parseRPM(rpmResponse);
                        Thread.sleep(500);

                        sendOBD2Command("012F");
                        String fuelResponse = readOBD2Response();
                        fuelLevel = parseFuelLevel(fuelResponse);
                        Thread.sleep(500);

                        runOnUiThread(() -> {
                            speedTextView.setText("Velocidad: " + vehicleSpeed + " km/h");
                            rpmTextView.setText("RPM: " + rpm);
                            fuelLevelTextView.setText("Nivel de Combustible: " + fuelLevel + "%");
                        });
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Error en la comunicación OBD-II: " + e.getMessage());
                }

                handler.postDelayed(this, delay);
            }
        }, delay);
    }

    private void startLocationUpdates() {
        LocationRequest locationRequest = LocationRequest.create();
        locationRequest.setPriority(LocationRequest.PRIORITY_HIGH_ACCURACY);
        locationRequest.setInterval(10000);

        locationCallback = new LocationCallback() {
            @Override
            public void onLocationResult(LocationResult locationResult) {
                if (locationResult == null) return;
                for (Location location : locationResult.getLocations()) {
                    if (location != null) {
                        String stringLatitude = Double.toString(location.getLatitude());
                        String stringLongitude = Double.toString(location.getLongitude());
                        String timestamp = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(new Date(location.getTime()));
                        String message = " ID: " + client_id + " Latitude: " + stringLatitude + " Longitude: " + stringLongitude +
                                " Timestamp: " + timestamp + " Speed: " + vehicleSpeed + " RPM: " + rpm + " Fuel: " + fuelLevel;

                        if (selectedMode.equals("GPS y OBD") || selectedMode.equals("Solo GPS")) {
                            for (String ip : ipAWS) {
                                sendLocationToIp(ip, puertoTCP, message);
                            }
                        }

                        textView.setText("Latitude: " + stringLatitude + " Longitude: " + stringLongitude);
                    }
                }
            }
        };

        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED &&
                ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        fusedLocationProviderClient.requestLocationUpdates(locationRequest, locationCallback, null);
    }

    private void stopLocationUpdates() {
        if (fusedLocationProviderClient != null && locationCallback != null) {
            fusedLocationProviderClient.removeLocationUpdates(locationCallback);
        }
    }

    private void sendLocationToIp(final String ip, final int port, final String message) {
        new Thread(() -> {
            try (Socket socket = new Socket(ip, port);
                 OutputStream outputStream = socket.getOutputStream()) {
                outputStream.write(message.getBytes());
                outputStream.flush();
            } catch (Exception e) {
                Log.e(TAG, "Error al enviar mensaje: " + e.getMessage());
            }
        }).start();
    }

    private void sendOBD2Command(String command) throws IOException {
        command += "\r";
        outputStream.write(command.getBytes());
        outputStream.flush();
    }

    private String readOBD2Response() throws IOException {
        byte[] buffer = new byte[1024];
        StringBuilder responseBuilder = new StringBuilder();
        int attempts = 0;

        // Reintentar la lectura mientras no haya respuesta y un máximo de 5 intentos
        while (attempts < 5) {
            if (inputStream.available() > 0) {
                int bytesRead = inputStream.read(buffer);
                String part = new String(buffer, 0, bytesRead).trim();
                responseBuilder.append(part);

                if (part.contains(">")) { // Fin de respuesta
                    break;
                }
            } else {
                attempts++;
                try {
                    Thread.sleep(500);  // Espera breve antes de reintentar
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
        }

        return responseBuilder.toString().trim();
    }

    private int parseSpeed(String response) {
        response = response.replace("SEARCHING...", "").replace(">", "").trim();
        String[] parts = response.split("\\s+");

        for (int i = 0; i < parts.length; i++) {
            if (parts[i].equals("41") && i + 2 < parts.length && parts[i + 1].equals("0D")) {
                try {
                    return Integer.parseInt(parts[i + 2], 16);
                } catch (NumberFormatException e) {
                    Log.e(TAG, "Error al parsear velocidad: " + e.getMessage());
                }
            }
        }
        return 0;
    }

    private int parseRPM(String response) {
        response = response.replace("SEARCHING...", "").replace(">", "").trim();
        String[] parts = response.split("\\s+");

        for (int i = 0; i < parts.length; i++) {
            if (parts[i].equals("41") && (i + 1 < parts.length) && parts[i + 1].equals("0C") && (i + 3 < parts.length)) {
                try {
                    String hexA = parts[i + 2];
                    String hexB = parts[i + 3];
                    return ((Integer.parseInt(hexA, 16) * 256) + Integer.parseInt(hexB, 16)) / 4;
                } catch (NumberFormatException e) {
                    Log.e(TAG, "Error al parsear RPM: " + e.getMessage());
                }
            }
        }
        return 0;
    }
    private int parseFuelLevel(String response) {
        response = response.replace("SEARCHING...", "").replace(">", "").trim();
        String[] parts = response.split("\\s+");

        for (int i = 0; i < parts.length; i++) {
            if (parts[i].equals("41") && (i + 1 < parts.length) && parts[i + 1].equals("2F") && (i + 2 < parts.length)) {
                try {
                    int fuelHex = Integer.parseInt(parts[i + 2], 16);
                    return (fuelHex * 100) / 255;
                } catch (NumberFormatException e) {
                    Log.e(TAG, "Error al parsear el nivel de combustible: " + e.getMessage());
                }
            }
        }
        return 0; // Devuelve 0 si no se puede obtener el nivel de combustible
    }
    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            if (inputStream != null) inputStream.close();
            if (outputStream != null) outputStream.close();
            if (bluetoothSocket != null) bluetoothSocket.close();
            fusedLocationProviderClient.removeLocationUpdates(locationCallback);
        } catch (IOException e) {
            Log.e(TAG, "Error al cerrar streams: " + e.getMessage());
        }
    }
}
