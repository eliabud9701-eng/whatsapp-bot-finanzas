from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
import os

app = Flask(__name__)

# Base de datos simple en archivo JSON
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

def procesar_comando(mensaje, datos):
    msg = mensaje.lower().strip()
    
    # RESUMEN
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

💳 Total deudas: {fmt(total_deudas)}

Escribe *deudas* para ver el detalle de cada deuda."""

    # DEUDAS
    elif any(x in msg for x in ['deudas', 'cuanto debo', 'cuánto debo']):
        lines = ['💳 *MIS DEUDAS*\n']
        for nombre, info in datos['deudas'].items():
            if info['saldo'] > 0:
                meses = int(info['saldo'] / info['pago']) if info['pago'] > 0 else '?'
                lines.append(f"• {nombre}: {fmt(info['saldo'])} ({meses} meses)")
        return '\n'.join(lines)

    # INGRESO - "entró 50000 venta" o "ingreso 50000 comision"
    elif any(x in msg for x in ['entró', 'entro', 'ingreso', 'ingresó', 'ingreso']):
        palabras = msg.split()
        monto = 0
        for p in palabras:
            try:
                monto = float(p.replace(',', '').replace('$', ''))
                break
            except:
                continue
        if monto > 0:
            # Extraer fuente (todo después del monto)
            fuente = mensaje
            for p in palabras:
                try:
                    float(p.replace(',', '').replace('$', ''))
                    idx = palabras.index(p)
                    fuente = ' '.join(palabras[idx+1:]) if idx+1 < len(palabras) else 'Sin especificar'
                    break
                except:
                    continue
            datos['ingresos'].append({'monto': monto, 'fuente': fuente})
            guardar_datos(datos)
            total = sum(i['monto'] for i in datos['ingresos'])
            jomesh = int(monto * 0.2)
            return f"""✅ *Ingreso registrado*

💰 {fmt(monto)} de {fuente}
🕍 Jomesh a dar: {fmt(jomesh)}
📊 Total ingresos del mes: {fmt(total)}"""
        else:
            return '❌ No entendí el monto. Escribe por ejemplo: *entró 50000 venta cliente*'

    # PAGO DEUDA - "pagué 10000 a victor" o "abono 10000 amex"
    elif any(x in msg for x in ['pagué', 'pague', 'abono', 'aboné', 'aboner']):
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
            saldo_restante = datos['deudas'][deuda_encontrada]['saldo']
            return f"""✅ *Pago registrado*

💳 {deuda_encontrada}: -{fmt(monto)}
📊 Saldo restante: {fmt(saldo_restante)}"""
        elif monto > 0:
            return f'❌ No encontré la deuda. Las deudas disponibles son: {", ".join(datos["deudas"].keys())}'
        else:
            return '❌ No entendí el monto. Escribe por ejemplo: *pagué 10000 a Victor*'

    # PAGAR GASTO - "pagué renta" o "pague seguro"
    elif any(x in msg for x in ['pagué', 'pague']):
        for gasto in datos['gastos_fijos'].keys():
            if gasto.lower() in msg:
                if gasto not in datos['gastos_pagados']:
                    datos['gastos_pagados'].append(gasto)
                    guardar_datos(datos)
                return f'✅ *{gasto}* marcado como pagado — {fmt(datos["gastos_fijos"][gasto])}'
        return '❌ No encontré ese gasto. Escribe *gastos* para ver la lista.'

    # GASTOS
    elif any(x in msg for x in ['gastos', 'que debo pagar', 'qué debo pagar']):
        lines = ['🧾 *GASTOS FIJOS*\n']
        for nombre, monto in datos['gastos_fijos'].items():
            estado = '✅' if nombre in datos['gastos_pagados'] else '⏳'
            lines.append(f"{estado} {nombre}: {fmt(monto)}")
        total = sum(datos['gastos_fijos'].values())
        pagado = sum(datos['gastos_fijos'][g] for g in datos['gastos_pagados'] if g in datos['gastos_fijos'])
        lines.append(f'\n💰 Pagado: {fmt(pagado)} / {fmt(total)}')
        return '\n'.join(lines)

    # JOMESH
    elif 'jomesh' in msg:
        total_ingresos = sum(i['monto'] for i in datos['ingresos'])
        jomesh = int(total_ingresos * 0.2)
        return f"""🕍 *JOMESH*

💰 Ingresos del mes: {fmt(total_ingresos)}
🕍 Jomesh a dar (20%): {fmt(jomesh)}

Escribe *pagué jomesh 10000 sinagoga* para registrar un pago."""

    # RESET MES
    elif any(x in msg for x in ['nuevo mes', 'reset', 'reiniciar']):
        datos['ingresos'] = []
        datos['gastos_pagados'] = []
        guardar_datos(datos)
        return '✅ Mes reiniciado. Ingresos y pagos borrados. Las deudas se mantienen.'

    # AYUDA
    else:
        return """🤖 *BOT DE FINANZAS*

Comandos disponibles:

📊 *resumen* — ver tu situación del mes
💳 *deudas* — ver saldo de cada deuda
🧾 *gastos* — ver gastos fijos del mes
🕍 *jomesh* — ver cuánto debes dar

💰 *entró 50000 venta* — registrar ingreso
✅ *pagué renta* — marcar gasto como pagado
💳 *pagué 10000 a Victor* — abonar a deuda

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
