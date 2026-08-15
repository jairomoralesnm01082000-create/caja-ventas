import datetime
import json
import os
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Ruta del archivo de datos dentro de la misma carpeta
DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_DATOS = os.path.join(DIRECTORIO_ACTUAL, "ventas_gastos_duenos.json")

# Lista de las 3 dueñas
DUENOS = ["BERTHA", "KARLA", "CARLITA"]

FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"


def cargar_datos():
    """Lee el archivo JSON de transacciones."""
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def guardar_datos(datos):
    """Guarda las transacciones en el archivo JSON."""
    with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)


@app.route("/")
def inicio():
    """Entrega la interfaz web."""
    return render_template("index.html", duenos=DUENOS)


@app.route("/api/datos", methods=["GET"])
def obtener_datos():
    """Devuelve las ventas y gastos guardados."""
    return jsonify(cargar_datos())


@app.route("/api/registrar", methods=["POST"])
def registrar_operacion():
    """Guarda una venta o gasto enviado desde la interfaz."""
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
    """Marca un fiado pendiente como cobrado."""
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
    """Elimina un registro individual."""
    payload = request.json
    registro_id = int(payload.get("id"))
    datos = cargar_datos()
    datos = [d for d in datos if d.get("id") != registro_id]
    guardar_datos(datos)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)