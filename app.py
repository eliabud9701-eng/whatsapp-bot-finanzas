from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
import re

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
        'gastos_variables': [],
        'deudas': {},
        'gastos_fijos': {}
    }

def guardar_datos(datos):
    with open(DB_FILE, 'w') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def fmt(n):
    try:
        return f'${int(float(n)):,}'
    except:
        return '$0'

def extraer_monto(texto):
    """Extrae el monto de un texto en lenguaje natural"""
    texto = texto.lower()
    # Reemplazar palabras por números
    texto = texto.replace('un mil', '1000').replace('dos mil', '2000')
    texto = texto.replace('tres mil', '3000').replace('cuatro mil', '4000')
    texto = texto.replace('cinco mil', '5000').replace('diez mil', '10000')
    texto = texto.replace('veinte mil', '20000').replace('cincuenta mil', '50000')
    texto = texto.replace('cien mil', '100000').replace('doscientos mil', '200000')
    texto = texto.replace('millón', '1000000').replace('millon', '1000000')
    texto = texto.replace('medio millón', '500000').replace('medio millon', '500000')

    # Buscar patrones como "50 mil", "3 mil", "1.5 millones"
    patron_mil = re.search(r'(\d+\.?\d*)\s*mil', texto)
    patron_millon = re.search(r'(\d+\.?\d*)\s*millon', texto)
    patron_normal = re.search(r'[\$]?\s*(\d{1,3}(?:[,.]?\d{3})*(?:\.\d+)?)', texto)

    if patron_millon:
        return float(patron_millon.group(1)) * 1000000
    elif patron_mil:
        return float(patron_mil.group(1)) * 1000
    elif patron_normal:
        num = patron_normal.group(1).replace(',', '')
        return float(num)
    return 0

def detectar_intencion(mensaje):
    """Detecta la intención del mensaje sin IA"""
    msg = mensaje.lower().strip()
    
    # Palabras clave por intención
    palabras_ingreso = ['entró', 'entro', 'cobré', 'cobre', 'recibí', 'recibi', 
                        'me pagaron', 'me pago', 'ingresó', 'ingreso', 'gané', 'gane',
                        'depositar', 'depósito', 'deposito', 'cobrar', 'venta',
                        'comisión', 'comision', 'pago de', 'me cayó', 'cayó']
    
    palabras_gasto = ['gasté', 'gaste', 'compré', 'compre', 'pagué', 'pague',
                      'costó', 'costo', 'salió', 'salio', 'gastar', 'comprar',
                      'fui al', 'fui a', 'comí', 'comi', 'cené', 'cene',
                      'taxi', 'uber', 'gasolina', 'gas', 'super', 'mercado',
                      'farmacia', 'doctor', 'médico', 'restaurante', 'comida']
    
    palabras_deuda_pago = ['abono', 'aboné', 'abone', 'pagué a', 'pague a',
                           'le pagué', 'le pague', 'abonando', 'quité', 'quite']
    
    palabras_nueva_deuda = ['le debo', 'debo', 'quedé a deber', 'quede a deber',
                            'me prestó', 'me presto', 'me prestaron', 'nueva deuda',
                            'deuda con', 'deuda de', 'préstamo', 'prestamo']
    
    palabras_nuevo_gasto_fijo = ['mi renta es', 'renta es', 'pago de renta',
                                  'mensualmente pago', 'cada mes pago', 'fijo mensual',
                                  'gasto fijo', 'agregar gasto']
    
    palabras_resumen = ['resumen', 'cómo voy', 'como voy', 'estado', 'situación',
                        'situacion', 'mis finanzas', 'cuánto tengo', 'cuanto tengo',
                        'disponible', 'cuánto me queda', 'cuanto me queda']
    
    palabras_deudas = ['deudas', 'cuánto debo', 'cuanto debo', 'mis deudas',
                       'lo que debo', 'deudores']
    
    palabras_gastos = ['gastos', 'mis gastos', 'qué debo pagar', 'que debo pagar',
                       'gastos fijos', 'pagos pendientes']
    
    palabras_jomesh = ['jomesh', 'diezmo', 'tzedaka', 'tzedaká', 'caridad',
                       'donación', 'donacion', 'cuánto doy', 'cuanto doy']
    
    palabras_nuevo_mes = ['nuevo mes', 'reiniciar', 'reset', 'empezar mes',
                          'mes nuevo', 'cerrar mes']

    if any(p in msg for p in palabras_nuevo_mes):
        return 'NUEVO_MES'
    if any(p in msg for p in palabras_jomesh):
        return 'JOMESH'
    if any(p in msg for p in palabras_resumen):
        return 'RESUMEN'
    if any(p in msg for p in palabras_deudas):
        return 'DEUDAS'
    if any(p in msg for p in palabras_gastos):
        return 'GASTOS'
    if any(p in msg for p in palabras_deuda_pago):
        return 'PAGO_DEUDA'
    if any(p in msg for p in palabras_nueva_deuda):
        return 'NUEVA_DEUDA'
    if any(p in msg for p in palabras_nuevo_gasto_fijo):
        return 'NUEVO_GASTO_FIJO'
    if any(p in msg for p in palabras_ingreso):
        return 'INGRESO'
    if any(p in msg for p in palabras_gasto):
        return 'GASTO_VARIABLE'
    
    return 'AYUDA'

def procesar_mensaje(mensaje, datos):
    msg = mensaje.lower().strip()
    intencion = detectar_intencion(mensaje)
    monto = extraer_monto(mensaje)

    # INGRESO
    if intencion == 'INGRESO':
        if monto > 0:
            # Extraer fuente (todo excepto números y palabras clave)
            fuente = re.sub(r'\d+[\.,]?\d*\s*(mil|miles|millon|millones)?', '', msg)
            fuente = re.sub(r'entró|entro|cobré|cobre|recibí|recibi|me pagaron|ingresó|ingreso|gané|gane|de|pesos|dlls|usd|mxn', '', fuente)
            fuente = fuente.strip() or 'Sin especificar'
            datos.setdefault('ingresos', []).append({'monto': monto, 'fuente': fuente})
            guardar_datos(datos)
            total = sum(i.get('monto', 0) for i in datos['ingresos'])
            jomesh = int(monto * 0.2)
            return f"""✅ *Ingreso registrado*

💰 {fmt(monto)} de {fuente}
🕍 Jomesh a dar: {fmt(jomesh)}
📊 Total ingresos del mes: {fmt(total)}"""
        return '❌ No entendí el monto. Ej: *Me pagaron 50 mil de una venta*'

    # GASTO VARIABLE
    elif intencion == 'GASTO_VARIABLE':
        if monto > 0:
            # Extraer descripción
            desc = re.sub(r'\d+[\.,]?\d*\s*(mil|miles|millon|millones)?', '', msg)
            desc = re.sub(r'gasté|gaste|compré|compre|pagué|pague|costó|costo|en|pesos', '', desc)
            desc = desc.strip() or 'gasto general'
            datos.setdefault('gastos_variables', []).append({'monto': monto, 'descripcion': desc})
            guardar_datos(datos)
            return f'✅ *Gasto registrado*\n\n💸 {fmt(monto)} en {desc}'
        return '❌ No entendí el monto. Ej: *Gasté 3,000 en el super*'

    # PAGO DEUDA
    elif intencion == 'PAGO_DEUDA':
        if monto > 0:
            deuda_key = None
            for k in datos.get('deudas', {}).keys():
                if k.lower() in msg:
                    deuda_key = k
                    break
            if deuda_key:
                datos['deudas'][deuda_key]['saldo'] = max(0, datos['deudas'][deuda_key]['saldo'] - monto)
                guardar_datos(datos)
                return f"""✅ *Pago registrado*

💳 {deuda_key}: -{fmt(monto)}
📊 Saldo restante: {fmt(datos['deudas'][deuda_key]['saldo'])}"""
            else:
                deudas_lista = ', '.join(datos.get('deudas', {}).keys()) or 'ninguna'
                return f'❌ ¿A cuál deuda? Tus deudas: {deudas_lista}'
        return '❌ No entendí el monto. Ej: *Abono 5,000 a Amex*'

    # NUEVA DEUDA
    elif intencion == 'NUEVA_DEUDA':
        if monto > 0:
            # Extraer nombre
            nombre = re.sub(r'\d+[\.,]?\d*\s*(mil|miles|millon|millones)?', '', msg)
            nombre = re.sub(r'le debo|debo|me prestó|me presto|me prestaron|nueva deuda|deuda con|de|pesos', '', nombre)
            nombre = nombre.strip() or 'Nueva deuda'
            datos.setdefault('deudas', {})[nombre] = {'saldo': monto, 'pago': 0}
            guardar_datos(datos)
            return f'✅ *Deuda registrada*\n\n💳 {nombre}: {fmt(monto)}'
        return '❌ No entendí el monto. Ej: *Le debo 20,000 a Juan*'

    # NUEVO GASTO FIJO
    elif intencion == 'NUEVO_GASTO_FIJO':
        if monto > 0:
            nombre = re.sub(r'\d+[\.,]?\d*\s*(mil|miles|millon|millones)?', '', msg)
            nombre = re.sub(r'mi renta es|renta es|mensualmente pago|cada mes pago|fijo mensual|gasto fijo|agregar gasto|de|pesos|al mes', '', nombre)
            nombre = nombre.strip() or 'Nuevo gasto fijo'
            datos.setdefault('gastos_fijos', {})[nombre] = monto
            guardar_datos(datos)
            return f'✅ *Gasto fijo agregado*\n\n🧾 {nombre}: {fmt(monto)}/mes'
        return '❌ No entendí el monto. Ej: *Mi renta es 15,000 al mes*'

    # RESUMEN
    elif intencion == 'RESUMEN':
        total_ingresos = sum(i.get('monto', 0) for i in datos.get('ingresos', []))
        total_deudas = sum(d.get('saldo', 0) for d in datos.get('deudas', {}).values())
        jomesh = int(total_ingresos * 0.2)
        total_gastos_fijos = sum(datos.get('gastos_fijos', {}).values())
        total_gastos_var = sum(g.get('monto', 0) for g in datos.get('gastos_variables', []))
        disponible = total_ingresos - jomesh - total_gastos_fijos - total_gastos_var
        return f"""📊 *RESUMEN ORDENA*

💰 Ingresos: {fmt(total_ingresos)}
🕍 Jomesh (20%): {fmt(jomesh)}
🧾 Gastos fijos: {fmt(total_gastos_fijos)}
💸 Gastos variables: {fmt(total_gastos_var)}
💵 Disponible: {fmt(disponible)}
💳 Total deudas: {fmt(total_deudas)}"""

    # DEUDAS
    elif intencion == 'DEUDAS':
        deudas = datos.get('deudas', {})
        if not deudas:
            return '💳 No tienes deudas. Escríbeme: *Le debo 50,000 a Juan*'
        lines = ['💳 *MIS DEUDAS*\n']
        for nombre, info in deudas.items():
            saldo = info.get('saldo', 0)
            pago = info.get('pago', 0)
            meses = int(saldo / pago) if pago > 0 else '?'
            lines.append(f'• {nombre}: {fmt(saldo)}' + (f' (~{meses} meses)' if pago > 0 else ''))
        total = sum(d.get('saldo', 0) for d in deudas.values())
        lines.append(f'\n💳 Total: {fmt(total)}')
        return '\n'.join(lines)

    # GASTOS
    elif intencion == 'GASTOS':
        gastos = datos.get('gastos_fijos', {})
        if not gastos:
            return '🧾 No tienes gastos fijos. Escríbeme: *Mi renta es 15,000 al mes*'
        lines = ['🧾 *GASTOS FIJOS*\n']
        for nombre, monto_g in gastos.items():
            estado = '✅' if nombre in datos.get('gastos_pagados', []) else '⏳'
            lines.append(f'{estado} {nombre}: {fmt(monto_g)}')
        total = sum(gastos.values())
        pagado = sum(gastos[g] for g in datos.get('gastos_pagados', []) if g in gastos)
        lines.append(f'\n💰 Pagado: {fmt(pagado)} / {fmt(total)}')
        return '\n'.join(lines)

    # JOMESH
    elif intencion == 'JOMESH':
        total_ingresos = sum(i.get('monto', 0) for i in datos.get('ingresos', []))
        jomesh = int(total_ingresos * 0.2)
        return f"""🕍 *JOMESH*

💰 Ingresos del mes: {fmt(total_ingresos)}
🕍 Jomesh a dar (20%): {fmt(jomesh)}

Escribe *pagué jomesh* para registrar un pago."""

    # NUEVO MES
    elif intencion == 'NUEVO_MES':
        datos['ingresos'] = []
        datos['gastos_pagados'] = []
        datos['gastos_variables'] = []
        guardar_datos(datos)
        return '✅ *Mes reiniciado*\n\nIngresos, gastos variables y pagos borrados. Las deudas se mantienen.'

    # AYUDA
    else:
        return """👋 *Hola! Soy Ordena* 🤖

Tu asistente financiero. Escríbeme en español natural:

💬 *Ejemplos:*
• "Gasté 3,000 en el super"
• "Me pagaron 50 mil de una venta"
• "Le debo 20,000 a Juan"
• "Abono 5,000 a Amex"
• "Mi renta es 15,000 al mes"
• "Resumen del mes"
• "Mis deudas"
• "Jomesh"

¡Escríbeme como le escribirías a un amigo! 😊"""

# ── API ────────────────────────────────────────────────────────

@app.route('/api/datos', methods=['GET'])
def get_datos():
    return jsonify(cargar_datos())

@app.route('/api/datos', methods=['POST'])
def set_datos():
    guardar_datos(request.json)
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset_mes():
    datos = cargar_datos()
    datos['ingresos'] = []
    datos['gastos_pagados'] = []
    datos['gastos_variables'] = []
    guardar_datos(datos)
    return jsonify({'ok': True})

# ── WHATSAPP ──────────────────────────────────────────────────

@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    mensaje = request.form.get('Body', '').strip()
    print(f'Mensaje recibido: {mensaje}')
    datos = cargar_datos()
    respuesta = procesar_mensaje(mensaje, datos)
    print(f'Respuesta: {respuesta[:50]}')
    resp = MessagingResponse()
    resp.message(respuesta)
    return str(resp)

@app.route('/')
def index():
    return '✅ Ordena Bot activo'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
