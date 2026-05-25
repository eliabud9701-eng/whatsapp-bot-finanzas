from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import json
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'finanzas.json'

def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {
        'ingresos': [],
        'gastos_pagados': [],
        'deudas': {
            'Victor': {'saldo': 45000, 'pago': 20000},
            'Dani Levy': {'saldo': 40000, 'pago': 10000},
            'Samy': {'saldo': 40000, 'pago': 8000},
            'Amex': {'saldo': 180000, 'pago': 20000},
            'Ovadia': {'saldo': 62000, 'pago': 0},
        },
        'gastos_fijos': {
            'Renta': 21000,
            'Seguro': 13103,
            'Colegiatura': 6700,
            'Muchacha': 8000,
            'Gas y Luz': 9300,
            'Wegovy y Mounjaro': 9476,
            'Gym': 5200,
            'Piramides': 5000,
        }
    }

def guardar_datos(datos):
    with open(DB_FILE, 'w') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def fmt(n):
    return f'${int(n):,}'

# ── API ENDPOINTS ─────────────────────────────────────────────

@app.route('/api/datos', methods=['GET'])
def get_datos():
    datos = cargar_datos()
    return jsonify(datos)

@app.route('/api/datos', methods=['POST'])
def set_datos():
    datos = request.json
    guardar_datos(datos)
    return jsonify({'ok': True})

@app.route('/api/ingreso', methods=['POST'])
def add_ingreso():
    datos = cargar_datos()
    body = request.json
    datos['ingresos'].append(body)
    guardar_datos(datos)
    return jsonify({'ok': True})

@app.route('/api/gasto-pagado', methods=['POST'])
def add_gasto_pagado():
    datos = cargar_datos()
    gasto = request.json.get('gasto')
    if gasto and gasto not in datos['gastos_pagados']:
        datos['gastos_pagados'].append(gasto)
    guardar_datos(datos)
    return jsonify({'ok': True})

@app.route('/api/deuda-pago', methods=['POST'])
def add_deuda_pago():
    datos = cargar_datos()
    body = request.json
    nombre = body.get('nombre')
    monto = body.get('monto', 0)
    if nombre in datos['deudas']:
        datos['deudas'][nombre]['saldo'] = max(0, datos['deudas'][nombre]['saldo'] - monto)
    guardar_datos(datos)
    return jsonify({'ok': True, 'saldo': datos['deudas'].get(nombre, {}).get('saldo', 0)})

@app.route('/api/reset', methods=['POST'])
def reset_mes():
    datos = cargar_datos()
    datos['ingresos'] = []
    datos['gastos_pagados'] = []
    guardar_datos(datos)
    return jsonify({'ok': True})

# ── WHATSAPP BOT ──────────────────────────────────────────────

def procesar_comando(mensaje, datos):
    msg = mensaje.lower().strip()

    if any(x in msg for x in ['resumen', 'estado', 'como voy', 'cómo voy']):
        total_ingresos = sum(i['monto'] for i in datos['ingresos'])
        total_deudas = sum(d['saldo'] for d in datos['deudas'].values())
        jomesh = int(total_ingresos * 0.2)
        total_gastos_fijos = sum(datos['gastos_fijos'].values())
        disponible = total_ingresos - jomesh - total_gastos_fijos
        return f"""📊 *RESUMEN FINANCIERO*

💰 Ingresos del mes: {fmt(total_ingresos)}
🕍 Jomesh (20%): {fmt(jomesh)}
🧾 Gastos fijos: {fmt(total_gastos_fijos)}
💵 Disponible: {fmt(disponible)}

💳 Total deudas: {fmt(total_deudas)}"""

    elif any(x in msg for x in ['deudas', 'cuanto debo', 'cuánto debo']):
        lines = ['💳 *MIS DEUDAS*\n']
        for nombre, info in datos['deudas'].items():
            if info['saldo'] > 0:
                meses = int(info['saldo'] / info['pago']) if info['pago'] > 0 else '?'
                lines.append(f"• {nombre}: {fmt(info['saldo'])} (~{meses} meses)")
        return '\n'.join(lines)

    elif any(x in msg for x in ['entró', 'entro', 'ingreso', 'ingresó']):
        palabras = msg.split()
        monto = 0
        fuente = 'Sin especificar'
        for i, p in enumerate(palabras):
            try:
                monto = float(p.replace(',', '').replace('$', ''))
                fuente = ' '.join(palabras[i+1:]) if i+1 < len(palabras) else 'Sin especificar'
                break
            except:
                continue
        if monto > 0:
            datos['ingresos'].append({'monto': monto, 'fuente': fuente})
            guardar_datos(datos)
            total = sum(i['monto'] for i in datos['ingresos'])
            jomesh = int(monto * 0.2)
            return f"""✅ *Ingreso registrado*

💰 {fmt(monto)} de {fuente}
🕍 Jomesh a dar: {fmt(jomesh)}
📊 Total ingresos del mes: {fmt(total)}"""
        return '❌ No entendí el monto. Ej: *entró 50000 venta cliente*'

    elif any(x in msg for x in ['pagué', 'pague', 'abono', 'aboné']):
        palabras = msg.split()
        monto = 0
        for p in palabras:
            try:
                monto = float(p.replace(',', '').replace('$', ''))
                break
            except:
                continue

        deuda_encontrada = None
        for nombre in datos['deudas'].keys():
            if nombre.lower() in msg:
                deuda_encontrada = nombre
                break

        if monto > 0 and deuda_encontrada:
            datos['deudas'][deuda_encontrada]['saldo'] = max(0, datos['deudas'][deuda_encontrada]['saldo'] - monto)
            guardar_datos(datos)
            return f"""✅ *Pago a {deuda_encontrada}*

💳 -{fmt(monto)}
📊 Saldo restante: {fmt(datos['deudas'][deuda_encontrada]['saldo'])}"""

        if monto == 0:
            for gasto in datos['gastos_fijos'].keys():
                if gasto.lower() in msg:
                    if gasto not in datos['gastos_pagados']:
                        datos['gastos_pagados'].append(gasto)
                        guardar_datos(datos)
                    return f'✅ *{gasto}* marcado como pagado — {fmt(datos["gastos_fijos"][gasto])}'

        return '❌ No entendí. Ej: *pagué renta* o *pagué 10000 a Victor*'

    elif any(x in msg for x in ['gastos', 'que debo pagar']):
        lines = ['🧾 *GASTOS FIJOS*\n']
        for nombre, monto in datos['gastos_fijos'].items():
            estado = '✅' if nombre in datos['gastos_pagados'] else '⏳'
            lines.append(f"{estado} {nombre}: {fmt(monto)}")
        total = sum(datos['gastos_fijos'].values())
        pagado = sum(datos['gastos_fijos'][g] for g in datos['gastos_pagados'] if g in datos['gastos_fijos'])
        lines.append(f'\n💰 Pagado: {fmt(pagado)} / {fmt(total)}')
        return '\n'.join(lines)

    elif 'jomesh' in msg:
        total_ingresos = sum(i['monto'] for i in datos['ingresos'])
        jomesh = int(total_ingresos * 0.2)
        return f"""🕍 *JOMESH*

💰 Ingresos del mes: {fmt(total_ingresos)}
🕍 Jomesh a dar (20%): {fmt(jomesh)}"""

    elif any(x in msg for x in ['nuevo mes', 'reset', 'reiniciar']):
        datos['ingresos'] = []
        datos['gastos_pagados'] = []
        guardar_datos(datos)
        return '✅ Mes reiniciado. Ingresos y pagos borrados.'

    else:
        return """🤖 *BOT DE FINANZAS*

📊 *resumen* — situación del mes
💳 *deudas* — saldo de cada deuda
🧾 *gastos* — gastos fijos del mes
🕍 *jomesh* — cuánto debes dar

💰 *entró 50000 venta* — registrar ingreso
✅ *pagué renta* — marcar gasto pagado
💳 *pagué 10000 a Victor* — abonar deuda
🔄 *nuevo mes* — reiniciar el mes"""

@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    mensaje = request.form.get('Body', '').strip()
    datos = cargar_datos()
    respuesta = procesar_comando(mensaje, datos)
    resp = MessagingResponse()
    resp.message(respuesta)
    return str(resp)

@app.route('/')
def index():
    return '✅ Bot de finanzas activo'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
