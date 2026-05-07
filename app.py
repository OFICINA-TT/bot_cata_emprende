import os
import json
import requests
import urllib.parse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
app = Flask("bot-cata-emprende")

# --- 1. CONFIGURACIÓN DESDE TU .ENV ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
EMAIL_BOT = os.getenv("EMAIL_BOT", "fm982020@gmail.com")
EMAIL_KATHY = os.getenv("EMAIL_KATHY")
EMAIL_OBSERVADOR = os.getenv("EMAIL_OBSERVADOR") # Correo de Fer
LINK_REUNION = os.getenv("LINK_REUNION", "https://asu.zoom.us/j/4172877924")
SERVICE_ACCOUNT_FILE = 'secretos_google.json'

SCOPES = ['https://www.googleapis.com/auth/calendar']

def obtener_servicio_google():
    # 1. Intentamos primero con la variable de entorno (Para Render)
    google_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    if google_json:
        try:
            # Si la variable existe, la transformamos de texto a JSON
            info = json.loads(google_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            print(f"Error leyendo la variable GOOGLE_CREDENTIALS_JSON: {e}")

    # 2. Si no hay variable, buscamos el archivo físico (Para tu Mac)
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('calendar', 'v3', credentials=creds)
    
    # 3. Si no hay ninguna de las dos, lanzamos el error
    raise Exception("No se encontraron credenciales de Google (ni en Render ni en el archivo local).")

service = obtener_servicio_google()

# --- 2. GENERADOR DE LINK CALENDARIO ---
def generar_link_google_calendar(nombre_equipo, hora_inicio_str):
    fecha = "20260508" # Viernes 08 de Mayo
    h_inicio = hora_inicio_str.replace(":", "") + "00"
    
    # Calculamos el fin (+30 min) para el link
    h, m = map(int, hora_inicio_str.split(':'))
    m_fin = m + 30
    h_fin = h
    if m_fin >= 60:
        h_fin += 1
        m_fin -= 60
    h_fin_str = f"{h_fin:02d}{m_fin:02d}00"

    titulo = urllib.parse.quote(f"Pitch Final: {nombre_equipo}")
    detalles = urllib.parse.quote(f"Evaluación CATA Emprende 2026. Link de Zoom: {LINK_REUNION}")
    ubicacion = urllib.parse.quote(LINK_REUNION)

    return f"https://www.google.com/calendar/render?action=TEMPLATE&text={titulo}&dates={fecha}T{h_inicio}/{fecha}T{h_fin_str}&details={detalles}&location={ubicacion}&ctz=America/Santiago"

# --- 3. LÓGICA DE CORREOS ---
def enviar_correos_confirmacion(email_equipo, nombre_equipo, hora_inicio):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }

    link_manual = generar_link_google_calendar(nombre_equipo, hora_inicio)

    # 1. DISEÑAMOS EL CONTENIDO (HTML)
    html_base = f"""
        <div style="font-family: Arial, sans-serif; color: #333; padding: 25px; border: 1px solid #eee; border-radius: 12px; max-width: 500px;">
            <h2 style="color: #1a252f;">[TITULO] 🚀</h2>
            <p>[MENSAJE]</p>
            <hr>
            <p><strong>Equipo:</strong> {nombre_equipo}</p>
            <p><strong>Contacto:</strong> {email_equipo}</p>
            <p><strong>Horario:</strong> Viernes 8 de Mayo, {hora_inicio} hrs.</p>
            <p><strong>Enlace de Zoom:</strong> <a href="{LINK_REUNION}">{LINK_REUNION}</a></p>
            <div style="margin-top: 25px; text-align: center;">
                <a href="{link_manual}" style="background-color: #4285F4; color: white; padding: 12px 25px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    📅 Ver en mi Calendario
                </a>
            </div>
        </div>
    """

    # 2. PREPARAMOS LOS DOS ENVÍOS

    # Envío A: Al Equipo (Confirmación)
    payload_equipo = {
        "sender": {"name": "BOT CATA EMPRENDE", "email": EMAIL_BOT}, 
        "to": [{"email": email_equipo}],
        "subject": f"Confirmación Mentoría: {nombre_equipo}",
        "htmlContent": html_base.replace("[TITULO]", "Confirmación de Mentoría").replace("[MENSAJE]", "Tu bloque para CATA Emprende ha sido reservado exitosamente.")
    }

    # Envío B: A Kathy y Fer (Aviso Interno) - AMBOS EN UN SOLO MAIL
    payload_staff = {
        "sender": {"name": "BOT CATA EMPRENDE", "email": EMAIL_BOT},
        "to": [
            {"email": EMAIL_KATHY},
            {"email": EMAIL_OBSERVADOR}
        ],
        "subject": f"NUEVO REGISTRO: {nombre_equipo}",
        "htmlContent": html_base.replace("[TITULO]", "Aviso de Coordinación").replace("[MENSAJE]", "Se ha registrado un nuevo equipo en el sistema.")
    }

    # 3. EJECUTAMOS LOS ENVÍOS
    res1 = requests.post(url, json=payload_equipo, headers=headers)
    res2 = requests.post(url, json=payload_staff, headers=headers)
    
    print(f"--- Reporte de Envíos ---")
    print(f"Envío a Equipo: {res1.status_code}")
    print(f"Envío a Staff (Kathy/Fer): {res2.status_code}")
    
# --- 4. LÓGICA DE GOOGLE CALENDAR ---
def crear_evento(nombre_equipo, email_equipo, hora_inicio_str):
    fecha_hoy = "2026-05-08" 
    start_dt = datetime.strptime(f"{fecha_hoy} {hora_inicio_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=30)
    
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:00-04:00")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:00-04:00")

    # Verificamos disponibilidad primero
    eventos_existentes = service.events().list(
        calendarId=EMAIL_KATHY, timeMin=start_iso, timeMax=end_iso, singleEvents=True
    ).execute()

    if eventos_existentes.get('items', []):
        raise Exception("Este bloque horario ya fue reservado.")

    # Configuramos el evento SIN 'attendees' para evitar el error de seguridad
    evento_body = {
        'summary': f'Pitch Final: {nombre_equipo}',
        'location': LINK_REUNION,
        'description': f'Evaluación CATA Emprende 2026.\nEquipo: {nombre_equipo}\nContacto: {email_equipo}\nCoordinadora: {EMAIL_OBSERVADOR}',
        'start': {'dateTime': start_iso, 'timeZone': 'America/Santiago'},
        'end': {'dateTime': end_iso, 'timeZone': 'America/Santiago'}
    }

    evento_creado = service.events().insert(
        calendarId=EMAIL_KATHY, 
        body=evento_body
    ).execute()
    
    return evento_creado.get('htmlLink')

# --- 5. FRONTEND Y RUTAS (Diseño del Formulario) ---
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

        <h2>Reserva de Mentoria</h2>
        <h3>Viernes 8 de Mayo</h3>
        
        <form id="formAgendar">
            <label for="equipo">Nombre del Equipo</label>
            <input type="text" id="equipo" placeholder="Ej: Innovadores" required>

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
                <option value="12:00">12:00 - 12:30 hrs</option>
                <option value="12:30">12:30 - 13:00 hrs</option>
                <option value="13:00">13:00 - 13:30 hrs</option>
                <option value="13:30">13:30 - 14:00 hrs</option>
            </select>

            <button type="submit" id="btnEnviar" disabled>Agendar Bloque</button>
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
                    resDiv.innerHTML = `<strong>¡Bloque Reservado!</strong><br>Revisa tu correo con el enlace de Zoom.`;
                    
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
                btn.innerText = "Agendar Bloque";
                btn.disabled = false;
            }
        });
    </script>
</body>
</html>
"""

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
            calendarId=EMAIL_KATHY, timeMin=start_iso, timeMax=end_iso, singleEvents=True
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
        enviar_correos_confirmacion(datos['email'], datos['equipo'], datos['hora'])
        return jsonify({"status": "success", "link": link}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000) 
