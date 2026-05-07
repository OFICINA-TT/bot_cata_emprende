import os
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
app = Flask("bot-cata-emprende")

# --- CONFIGURACIÓN ---
ID_CALENDARIO = "fernandaandreamesacarraco@gmail.com"
SERVICE_ACCOUNT_FILE = 'secretos_google.json' 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

SCOPES = ['https://www.googleapis.com/auth/calendar']

def obtener_servicio_google():
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    else:
        google_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not google_json:
            raise Exception("Credenciales no encontradas.")
        creds = service_account.Credentials.from_service_account_info(json.loads(google_json), scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

service = obtener_servicio_google()

# --- NUEVA LÓGICA DE CORREOS (BREVO) ---
def enviar_correos_confirmacion(email_equipo, nombre_equipo, hora_inicio):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }

# 1. CORREO PARA EL EQUIPO
    payload_equipo = {
        "sender": {"name": "Bot - CATA EMPRENDE", "email": ID_CALENDARIO},
        "to": [{"email": email_equipo}],
        "subject": f"Confirmación de Pitch: {nombre_equipo}",
        "htmlContent": f"""
            <h3>¡Hola {nombre_equipo}!</h3>
            <p>Tu sesión de pitch con Kathy ha sido agendada con éxito.</p>
            <p><strong>Fecha:</strong> Viernes 8 de Mayo<br>
               <strong>Hora:</strong> {hora_inicio} hrs</p>
            <p>Prontamente recibirás el enlace de conexión. ¡Mucho éxito!</p>
        """
    }

    # 2. CORREO PARA KATHY
    payload_kathy = {
        "sender": {"name": "Bot - CATA EMPRENDE", "email": ID_CALENDARIO},
        "to": [{"email": ID_CALENDARIO}],
        "subject": f"Nueva sesión agendada: {nombre_equipo}",
        "htmlContent": f"""
            <h3>Hola Kathy,</h3>
            <p>Se ha agendado una nueva reunión en tu calendario.</p>
            <p><strong>Equipo:</strong> {nombre_equipo}<br>
               <strong>Hora:</strong> {hora_inicio} hrs</p>
            <p><strong>Acción requerida:</strong> Por favor, envía el enlace de conexión al correo: {email_equipo}</p>
        """
    }

    # Enviamos ambos correos a la API de Brevo
# Enviamos ambos correos y guardamos la respuesta en res1 y res2
    res1 = requests.post(url, json=payload_equipo, headers=headers)
    res2 = requests.post(url, json=payload_kathy, headers=headers)

    # Imprimimos la respuesta en la terminal para descubrir el problema
    print("Respuesta Brevo Equipo:", res1.text)
    print("Respuesta Brevo Kathy:", res2.text)

# --- LÓGICA DEL CALENDARIO ---
def crear_evento(nombre_equipo, email_equipo, hora_inicio_str):
    fecha_hoy = "2026-05-08" 
    start_dt = datetime.strptime(f"{fecha_hoy} {hora_inicio_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=30)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:00-04:00")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:00-04:00")

    eventos_existentes = service.events().list(
        calendarId=ID_CALENDARIO, timeMin=start_iso, timeMax=end_iso, singleEvents=True
    ).execute()

    if eventos_existentes.get('items', []):
        raise Exception("Este bloque horario ya fue reservado.")

    evento_body = {
        'summary': f'Pitch: {nombre_equipo}',
        'description': f'Agendamiento automático. Contacto: {email_equipo}',
        'start': {'dateTime': start_iso, 'timeZone': 'America/Santiago'},
        'end': {'dateTime': end_iso, 'timeZone': 'America/Santiago'}
    }

    evento_creado = service.events().insert(calendarId=ID_CALENDARIO, body=evento_body).execute()
    return evento_creado.get('htmlLink')

# --- DISEÑO DEL FORMULARIO ---
HTML_FORM = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Oficina TT CATA - Agendamiento</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .container { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
        .logo-container { text-align: center; margin-bottom: 10px; }
        .logo-container img { max-width: 180px; height: auto; }
        h2 { color: #1a1a2e; text-align: center; margin-bottom: 5px; font-size: 22px; }
        h3 { color: #34495e; text-align: center; margin-top: 0; font-size: 16px; font-weight: normal; }
        label { display: block; margin-bottom: 5px; color: #4a4a4a; font-weight: bold; font-size: 14px; }
        input, select { width: 100%; padding: 10px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        option:disabled { color: #999999; background-color: #f2f2f2; font-style: italic; }
        button { width: 100%; padding: 12px; background-color: #2c3e50; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; transition: background 0.3s; }
        button:hover { background-color: #1a252f; }
        button:disabled { background-color: #95a5a6; cursor: not-allowed; }
        #resultado { margin-top: 20px; padding: 15px; border-radius: 6px; display: none; text-align: center; }
        .success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-container">
            <img src="/static/cata.jpeg" alt="Logo CATA">
        </div>
        <h2>Reserva de Mentoría</h2>
        <h3>Viernes 8 de Mayo</h3>
        
        <form id="formAgendar">
            <label for="equipo">Nombre del Equipo</label>
            <input type="text" id="equipo" placeholder="Ej: Los Innovadores" required>

            <label for="email">Email de contacto</label>
            <input type="email" id="email" placeholder="correo@ejemplo.com" required>

            <label for="hora">Selecciona tu horario</label>
            <select id="hora" required>
                <option value="" disabled selected>Cargando disponibilidad...</option>
                <option value="09:00">09:00 - 09:30 hrs</option>
                <option value="09:30">09:30 - 10:00 hrs</option>
                <option value="10:00">10:00 - 10:30 hrs</option>
                <option value="10:30">10:30 - 11:00 hrs</option>
                <option value="11:00">11:00 - 11:30 hrs</option>
                <option value="11:30">11:30 - 12:00 hrs</option>
            </select>

            <button type="submit" id="btnEnviar" disabled>Agendar ahora</button>
        </form>

        <div id="resultado"></div>
    </div>

    <script>
        window.onload = async () => {
            const selectHora = document.getElementById('hora');
            const btnEnviar = document.getElementById('btnEnviar');
            
            try {
                const response = await fetch('/disponibilidad');
                const data = await response.json();
                
                for (let i = 0; i < selectHora.options.length; i++) {
                    const option = selectHora.options[i];
                    if (data.ocupados.includes(option.value)) {
                        option.disabled = true;
                        option.text += ' (Ocupado)';
                    }
                }
                
                selectHora.options[0].text = "Elige un bloque de 30 min";
                btnEnviar.disabled = false; 
            } catch (error) {
                selectHora.options[0].text = "Error al cargar horarios";
            }
        };

        document.getElementById('formAgendar').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('btnEnviar');
            const resDiv = document.getElementById('resultado');
            
            btn.innerText = "Procesando...";
            btn.disabled = true;

            const datos = {
                equipo: document.getElementById('equipo').value,
                email: document.getElementById('email').value,
                hora: document.getElementById('hora').value
            };

            try {
                const response = await fetch('/agendar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(datos)
                });

                const result = await response.json();

                resDiv.style.display = "block";
                if (result.status === "success") {
                    resDiv.className = "success";
                    resDiv.innerHTML = `<strong>¡Bloque Reservado!</strong><br>El evento está en el calendario y se han enviado los correos.`;
                    
                    const select = document.getElementById('hora');
                    const optionSeleccionada = select.querySelector(`option[value="${datos.hora}"]`);
                    if (optionSeleccionada) {
                        optionSeleccionada.disabled = true;
                        optionSeleccionada.text += ' (Ocupado)';
                    }
                    select.value = ""; 
                    
                    document.getElementById('equipo').value = "";
                    document.getElementById('email').value = "";
                } else {
                    resDiv.className = "error";
                    resDiv.innerText = result.message;
                }
            } catch (error) {
                resDiv.style.display = "block";
                resDiv.className = "error";
                resDiv.innerText = "Error de conexión.";
            } finally {
                btn.innerText = "Agendar ahora";
                btn.disabled = false;
            }
        });
    </script>
</body>
</html>
"""

# --- RUTAS ---
@app.route('/')
def index():
    return render_template_string(HTML_FORM)

@app.route('/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha_hoy = "2026-05-08"
    start_iso = f"{fecha_hoy}T00:00:00-04:00"
    end_iso = f"{fecha_hoy}T23:59:59-04:00"

    try:
        eventos = service.events().list(
            calendarId=ID_CALENDARIO, timeMin=start_iso, timeMax=end_iso, singleEvents=True
        ).execute()

        ocupados = []
        for event in eventos.get('items', []):
            start = event['start'].get('dateTime')
            if start:
                hora_str = start.split('T')[1][:5]
                ocupados.append(hora_str)

        return jsonify({"ocupados": ocupados}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/agendar', methods=['POST'])
def agendar():
    datos = request.json
    try:
        link = crear_evento(datos['equipo'], datos['email'], datos['hora'])
        # AQUI ES DONDE DISPARAMOS EL CORREO
        enviar_correos_confirmacion(datos['email'], datos['equipo'], datos['hora'])
        return jsonify({"status": "success", "link": link}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
