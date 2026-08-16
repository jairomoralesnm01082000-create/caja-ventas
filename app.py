import csv
import datetime
import io
import json
import os
import urllib.request
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)

# Base de datos persistente en Firebase
FIREBASE_URL = "https://caja-ventas-default-rtdb.firebaseio.com"

# PIN de acceso de 4 dígitos
PIN_ACCESO = "0108"

DUENOS = ["BERTHA", "KARLA", "CARLITA"]
FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"


# ==========================================
# GESTIÓN DE DATOS EN LA NUBE (FIREBASE)
# ==========================================
def cargar_datos():
    """Lee las transacciones desde Firebase Realtime Database."""
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
    """Guarda las transacciones en Firebase permanentemente."""
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
# RUTAS DE LA APLICACIÓN WEB
# ==========================================
@app.route("/")
def inicio():
    return render_template("index.html", duenos=DUENOS)


@app.route("/api/verificar_pin", methods=["POST"])
def verificar_pin():
    payload = request.json
    pin_ingresado = payload.get("pin", "")
    if pin_ingresado == PIN_ACCESO:
        return jsonify({"status": "ok", "valido": True})
    return jsonify({"status": "error", "valido": False})


@app.route("/api/datos", methods=["GET"])
def obtener_datos():
    return jsonify(cargar_datos())


@app.route("/api/registrar", methods=["POST"])
def registrar_operacion():
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
        cliente = payload.get("cliente", "").strip()
        descripcion = payload.get("descripcion", "").strip()
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
            "metodo_cobro": "Yape" if metodo == "Yape" else None,
            "eliminado": False,
        }
    else:
        motivo = payload.get("motivo", "").strip()
        nuevo_registro = {
            "id": nuevo_id,
            "tipo": "Gasto",
            "dueno": dueno,
            "monto": monto,
            "motivo": motivo,
            "fecha": f"{fecha} 12:00:00",
            "eliminado": False,
        }

    datos.append(nuevo_registro)
    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/cobrar_fiado", methods=["POST"])
def cobrar_fiado():
    payload = request.json
    fiado_id = int(payload.get("id"))
    metodo_cobro = payload.get("metodo_cobro", "Yape")
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == fiado_id:
            d["cobrado"] = True
            d["metodo_cobro"] = metodo_cobro
            d["fecha_cobro"] = datetime.datetime.now().strftime(
                FORMATO_FECHA_HORA
            )
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/deshacer_cobro", methods=["POST"])
def deshacer_cobro():
    payload = request.json
    fiado_id = int(payload.get("id"))
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == fiado_id:
            d["cobrado"] = False
            d["metodo_cobro"] = None
            d["fecha_cobro"] = None
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/eliminar", methods=["POST"])
def eliminar_registro():
    """Mueve el registro a la papelera (Borrado lógico) para poder restaurarlo."""
    payload = request.json
    registro_id = int(payload.get("id"))
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == registro_id:
            d["eliminado"] = True
            d["fecha_eliminado"] = datetime.datetime.now().strftime(
                FORMATO_FECHA_HORA
            )
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/restaurar", methods=["POST"])
def restaurar_registro():
    """Restaura un registro eliminado de la papelera."""
    payload = request.json
    registro_id = int(payload.get("id"))
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == registro_id:
            d["eliminado"] = False
            d.pop("fecha_eliminado", None)
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/exportar_csv", methods=["GET"])
def exportar_csv():
    desde = request.args.get(
        "desde", datetime.datetime.now().strftime(FORMATO_FECHA)
    )
    hasta = request.args.get(
        "hasta", datetime.datetime.now().strftime(FORMATO_FECHA)
    )

    datos = cargar_datos()
    salida = io.StringIO()
    salida.write("\ufeff")

    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(
        [
            "ID",
            "Fecha",
            "Dueña",
            "Tipo",
            "Monto (S/.)",
            "Método Inicial",
            "Cliente / Motivo",
            "Descripción",
            "Estado Cobro",
            "Método de Cobro",
        ]
    )

    for d in datos:
        if d.get("eliminado", False):
            continue  # No exportar registros eliminados

        f = d.get("fecha", "")[:10]
        if desde <= f <= hasta:
            tipo = d.get("tipo", "")
            dueno = d.get("dueno", "")
            monto = f"{d.get('monto', 0):.2f}"
            metodo = d.get("metodo", "-")
            detalle = (
                d.get("cliente", "")
                if tipo == "Ingreso"
                else d.get("motivo", "")
            )
            desc = d.get("descripcion", "-")
            estado = (
                "Cobrado"
                if d.get("cobrado", True)
                else "Pendiente de Pago (Fiado)"
            )
            metodo_cobro = d.get("metodo_cobro", "-")

            escritor.writerow(
                [
                    d.get("id"),
                    f,
                    dueno,
                    tipo,
                    monto,
                    metodo,
                    detalle,
                    desc,
                    estado,
                    metodo_cobro,
                ]
            )

    salida.seek(0)
    nombre_archivo = f"reporte_caja_{desde}_al_{hasta}.csv"
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment;filename={nombre_archivo}"
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)