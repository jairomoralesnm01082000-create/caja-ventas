import datetime
import json
import os
import urllib.request
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Enlace de tu base de datos persistente en Firebase
FIREBASE_URL = "https://caja-ventas-default-rtdb.firebaseio.com"

DUENOS = ["BERTHA", "KARLA", "CARLITA"]
FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"


# ==========================================
# GESTIÓN DE DATOS EN LA NUBE (PERSISTENCIA)
# ==========================================
def cargar_datos():
    """Lee las transacciones directamente desde Firebase."""
    try:
        req = urllib.request.Request(f"{FIREBASE_URL}/transacciones.json")
        with urllib.request.urlopen(req, timeout=5) as response:
            contenido = response.read().decode("utf-8")
            if not contenido or contenido == "null":
                return []
            datos = json.loads(contenido)
            if isinstance(datos, list):
                return [d for d in datos if d is not None]
            elif isinstance(datos, dict):
                return list(datos.values())
            return []
    except Exception as e:
        print(f"Error al leer de Firebase: {e}")
        return []


def guardar_datos(datos):
    """Guarda las transacciones en Firebase de forma permanente."""
    try:
        data_json = json.dumps(datos).encode("utf-8")
        req = urllib.request.Request(
            f"{FIREBASE_URL}/transacciones.json",
            data=data_json,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            pass
    except Exception as e:
        print(f"Error al escribir en Firebase: {e}")


# ==========================================
# RUTAS DEL SERVIDOR WEB
# ==========================================
@app.route("/")
def inicio():
    """Entrega la pantalla principal."""
    return render_template("index.html", duenos=DUENOS)


@app.route("/api/datos", methods=["GET"])
def obtener_datos():
    """Devuelve todas las transacciones almacenadas en la base de datos."""
    return jsonify(cargar_datos())


@app.route("/api/registrar", methods=["POST"])
def registrar_operacion():
    """Registra una venta, fiado o gasto en la base de datos."""
    payload = request.json
    tipo = payload.get("tipo")
    dueno = payload.get("dueno")
    monto = float(payload.get("monto", 0))
    fecha = payload.get(
        "fecha", datetime.datetime.now().strftime(FORMATO_FECHA)
    )

    datos = cargar_datos()
    nuevo_id = max([d.get("id", 0) for d in datos], default=0) + 1

    if tipo == "Ingreso":
        metodo = payload.get("metodo")
        cliente = payload.get("cliente", "")
        descripcion = payload.get("descripcion", "")
        nuevo_registro = {
            "id": nuevo_id,
            "tipo": "Ingreso",
            "dueno": dueno,
            "monto": monto,
            "metodo": metodo,
            "cliente": cliente,
            "descripcion": descripcion,
            "fecha": f"{fecha} 12:00:00",
            "cobrado": True if metodo == "Yape" else False,
        }
    else:
        motivo = payload.get("motivo", "")
        nuevo_registro = {
            "id": nuevo_id,
            "tipo": "Gasto",
            "dueno": dueno,
            "monto": monto,
            "motivo": motivo,
            "fecha": f"{fecha} 12:00:00",
        }

    datos.append(nuevo_registro)
    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/cobrar_fiado", methods=["POST"])
def cobrar_fiado():
    """Marca un fiado pendiente como cobrado en la base de datos."""
    payload = request.json
    fiado_id = int(payload.get("id"))
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == fiado_id:
            d["cobrado"] = True
            d["metodo_cobro"] = "Yape"
            d["fecha_cobro"] = datetime.datetime.now().strftime(
                FORMATO_FECHA_HORA
            )
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/eliminar", methods=["POST"])
def eliminar_registro():
    """Elimina un registro individual de la base de datos."""
    payload = request.json
    registro_id = int(payload.get("id"))
    datos = cargar_datos()
    datos = [d for d in datos if d.get("id") != registro_id]
    guardar_datos(datos)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)