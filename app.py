from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
import requests

app = Flask(__name__)
CORS(app)

DB_FILE = 'finanzas.json'
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {
        'ingresos': [],
        'gastos_pagados': [],
        'deudas': {},
        'gastos_fijos': {}
    }

def guardar_datos(datos):
    with open(DB_FILE, 'w') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def fmt(n):
    return f'${int(n):,}'

def interpretar_con_ia(mensaje, datos):
    total_ingresos = sum(i.get('monto', 0) for i in datos.get('ingresos', []))
    total_deudas = sum(d.get('saldo', 0) for d in datos.get('deudas', {}).values())
    jomesh_deber = int(total_ingresos * 0.2)

    system_prompt = f"""Eres el asistente financiero de Ordena. Interpretas mensajes en español natural y ejecutas acciones financieras.

DATOS ACTUALES DEL USUARIO:
- Ingresos del mes: {fmt(total_ingresos)}
- Jomesh a dar (20%): {fmt(jomesh_deber)}
- Total deudas: {fmt(total_deudas)}
- Deudas: {json.dumps(datos.get('deudas', {}), ensure_ascii=False)}
- Gastos fijos: {json.dumps(datos.get('gastos_fijos', {}), ensure_ascii=False)}
- Gastos pagados este mes: {datos.get('gastos_pagados', [])}

INSTRUCCIONES:
Analiza el mensaje del usuario y responde con un JSON con este formato exacto:
{{
  "accion": "TIPO_ACCION",
  "datos": {{}},
  "respuesta": "Mensaje amigable para el usuario"
}}

TIPOS DE ACCION:
- "INGRESO": cuando menciona que entró dinero. datos: {{"monto": numero, "fuente": "descripcion"}}
- "PAGO_DEUDA": cuando abona a una deuda. datos: {{"nombre": "nombre_deuda", "monto": numero}}
- "PAGO_GASTO": cuando paga un gasto fijo. datos: {{"nombre": "nombre_gasto"}}
- "GASTO_VARIABLE": cuando gasta en algo no fijo. datos: {{"monto": numero, "descripcion": "descripcion"}}
- "NUEVA_DEUDA": cuando contrae una deuda nueva. datos: {{"nombre": "nombre", "saldo": numero, "pago": numero}}
- "NUEVO_GASTO": cuando agrega un gasto fijo nuevo. datos: {{"nombre": "nombre", "monto": numero}}
- "CONSULTA": cuando pregunta algo. datos: {{}}
- "RESUMEN": cuando pide resumen. datos: {{}}
- "DEUDAS": cuando pide ver deudas. datos: {{}}
- "GASTOS": cuando pide ver gastos. datos: {{}}
- "JOMESH": cuando pregunta por jomesh. datos: {{}}

EJEMPLOS:
- "gasté 3000 en el super" -> GASTO_VARIABLE
- "me pagaron 50 mil" -> INGRESO, monto: 50000
- "pagué la renta" -> PAGO_GASTO
- "le debo 20000 a mi primo juan" -> NUEVA_DEUDA
- "abono 5000 a amex" -> PAGO_DEUDA
- "cuánto tengo disponible" -> CONSULTA
- "cuánto debo de jomesh" -> JOMESH

Responde SOLO con el JSON, sin texto adicional."""

    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama3-8b-8192',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': mensaje}
                ],
                'max_tokens': 500,
                'temperature': 0.1
            }
        )
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        # Limpiar posibles backticks
        content = content.replace('```json', '').replace('```', '').strip()
        return json.loads(content)
    except Exception as e:
        print(f'Error Groq: {e}')
        return None

def ejecutar_accion(interpretacion, datos):
    if not interpretacion:
        return '❌ No pude entender tu mensaje. Intenta de nuevo.'

    accion = interpretacion.get('accion', '')
    d = interpretacion.get('datos', {})
    respuesta_ia = interpretacion.get('respuesta', '')

    if accion == 'INGRESO':
        monto = d.get('monto', 0)
        fuente = d.get('fuente', 'Sin especificar')
        if monto > 0:
            datos['ingresos'].append({'monto': monto, 'fuente': fuente})
            guardar_datos(datos)
            total = sum(i.get('monto', 0) for i in datos['ingresos'])
            jomesh = int(monto * 0.2)
            return f"""✅ *Ingreso registrado*

💰 {fmt(monto)} de {fuente}
🕍 Jomesh a dar: {fmt(jomesh)}
📊 Total ingresos del mes: {fmt(total)}"""

    elif accion == 'PAGO_DEUDA':
        nombre = d.get('nombre', '')
        monto = d.get('monto', 0)
        # Buscar deuda por nombre aproximado
        deuda_key = None
        for k in datos.get('deudas', {}).keys():
            if nombre.lower() in k.lower() or k.lower() in nombre.lower():
                deuda_key = k
                break
        if deuda_key and monto > 0:
            datos['deudas'][deuda_key]['saldo'] = max(0, datos['deudas'][deuda_key]['saldo'] - monto)
            guardar_datos(datos)
            return f"""✅ *Pago registrado*

💳 {deuda_key}: -{fmt(monto)}
📊 Saldo restante: {fmt(datos['deudas'][deuda_key]['saldo'])}"""
        elif monto > 0 and nombre:
            return f'❌ No encontré la deuda "{nombre}". Tus deudas son: {", ".join(datos.get("deudas", {}).keys())}'

    elif accion == 'PAGO_GASTO':
        nombre = d.get('nombre', '')
        gasto_key = None
        for k in datos.get('gastos_fijos', {}).keys():
            if nombre.lower() in k.lower() or k.lower() in nombre.lower():
                gasto_key = k
                break
        if gasto_key:
            if gasto_key not in datos['gastos_pagados']:
                datos['gastos_pagados'].append(gasto_key)
                guardar_datos(datos)
            return f'✅ *{gasto_key}* marcado como pagado — {fmt(datos["gastos_fijos"][gasto_key])}'
        return f'❌ No encontré ese gasto. {respuesta_ia}'

    elif accion == 'GASTO_VARIABLE':
        monto = d.get('monto', 0)
        desc = d.get('descripcion', 'gasto')
        if 'gastos_variables' not in datos:
            datos['gastos_variables'] = []
        datos['gastos_variables'].append({'monto': monto, 'descripcion': desc})
        guardar_datos(datos)
        return f'✅ *Gasto registrado*\n\n💸 {fmt(monto)} en {desc}'

    elif accion == 'NUEVA_DEUDA':
        nombre = d.get('nombre', 'Nueva deuda')
        saldo = d.get('saldo', 0)
        pago = d.get('pago', 0)
        datos.setdefault('deudas', {})[nombre] = {'saldo': saldo, 'pago': pago}
        guardar_datos(datos)
        return f'✅ *Deuda agregada*\n\n💳 {nombre}: {fmt(saldo)}'

    elif accion == 'NUEVO_GASTO':
        nombre = d.get('nombre', 'Nuevo gasto')
        monto = d.get('monto', 0)
        datos.setdefault('gastos_fijos', {})[nombre] = monto
        guardar_datos(datos)
        return f'✅ *Gasto fijo agregado*\n\n🧾 {nombre}: {fmt(monto)}/mes'

    elif accion == 'RESUMEN':
        total_ingresos = sum(i.get('monto', 0) for i in datos.get('ingresos', []))
        total_deudas = sum(d2.get('saldo', 0) for d2 in datos.get('deudas', {}).values())
        jomesh = int(total_ingresos * 0.2)
        total_gastos = sum(datos.get('gastos_fijos', {}).values())
        disponible = total_ingresos - jomesh - total_gastos
        return f"""📊 *RESUMEN ORDENA*

💰 Ingresos: {fmt(total_ingresos)}
🕍 Jomesh (20%): {fmt(jomesh)}
🧾 Gastos fijos: {fmt(total_gastos)}
💵 Disponible: {fmt(disponible)}
💳 Total deudas: {fmt(total_deudas)}"""

    elif accion == 'DEUDAS':
        deudas = datos.get('deudas', {})
        if not deudas:
            return '💳 No tienes deudas registradas. Escríbeme algo como: *le debo 50000 a Juan*'
        lines = ['💳 *MIS DEUDAS*\n']
        for nombre, info in deudas.items():
            meses = int(info['saldo'] / info['pago']) if info.get('pago', 0) > 0 else '?'
            lines.append(f"• {nombre}: {fmt(info['saldo'])} (~{meses} meses)")
        return '\n'.join(lines)

    elif accion == 'GASTOS':
        gastos = datos.get('gastos_fijos', {})
        if not gastos:
            return '🧾 No tienes gastos fijos registrados. Escríbeme algo como: *mi renta es 15000 al mes*'
        lines = ['🧾 *GASTOS FIJOS*\n']
        for nombre, monto in gastos.items():
            estado = '✅' if nombre in datos.get('gastos_pagados', []) else '⏳'
            lines.append(f"{estado} {nombre}: {fmt(monto)}")
        return '\n'.join(lines)

    elif accion == 'JOMESH':
        total_ingresos = sum(i.get('monto', 0) for i in datos.get('ingresos', []))
        jomesh = int(total_ingresos * 0.2)
        return f"""🕍 *JOMESH*

💰 Ingresos del mes: {fmt(total_ingresos)}
🕍 Jomesh a dar (20%): {fmt(jomesh)}"""

    elif accion == 'CONSULTA':
        return respuesta_ia or '🤖 ' + respuesta_ia

    return respuesta_ia or '🤖 Entendido. ¿En qué más te puedo ayudar?'

# ── API ENDPOINTS ─────────────────────────────────────────────

@app.route('/api/datos', methods=['GET'])
def get_datos():
    return jsonify(cargar_datos())

@app.route('/api/datos', methods=['POST'])
def set_datos():
    guardar_datos(request.json)
    return jsonify({'ok': True})

@app.route('/api/ingreso', methods=['POST'])
def add_ingreso():
    datos = cargar_datos()
    datos.setdefault('ingresos', []).append(request.json)
    guardar_datos(datos)
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset_mes():
    datos = cargar_datos()
    datos['ingresos'] = []
    datos['gastos_pagados'] = []
    guardar_datos(datos)
    return jsonify({'ok': True})

# ── WHATSAPP ──────────────────────────────────────────────────

@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    mensaje = request.form.get('Body', '').strip()
    datos = cargar_datos()

    # Comando de ayuda
    if mensaje.lower() in ['hola', 'help', 'ayuda', 'inicio', 'start']:
        respuesta = """👋 *Hola! Soy Ordena* 🤖

Tu asistente financiero inteligente. Escríbeme en español natural:

💬 *Ejemplos:*
• "Gasté 3,000 en el super"
• "Me pagaron 50 mil de una venta"
• "Pagué la renta"
• "Le debo 20,000 a mi primo"
• "Abono 5,000 a Amex"
• "Mi renta es 15,000 al mes"
• "Cuánto tengo disponible"
• "Resumen del mes"
• "Cuánto debo de jomesh"

¡Escríbeme como le escribirías a un amigo! 😊"""
    else:
        interpretacion = interpretar_con_ia(mensaje, datos)
        respuesta = ejecutar_accion(interpretacion, datos)

    resp = MessagingResponse()
    resp.message(respuesta)
    return str(resp)

@app.route('/')
def index():
    return '✅ Ordena Bot activo'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
