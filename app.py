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

# Zona horaria local (UTC-5 para Perú / Lima)
ZONA_HORARIA_OFFSET = datetime.timezone(datetime.timedelta(hours=-5))


def obtener_ahora_local():
    """Obtiene la fecha y hora local exacta en UTC-5."""
    return datetime.datetime.now(ZONA_HORARIA_OFFSET)


# ==========================================
# GESTIÓN DE DATOS EN LA NUBE (FIREBASE)
# ==========================================
def cargar_datos():
    """Lee las transacciones más recientes directamente desde Firebase."""
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
    monto = round(float(payload.get("monto", 0)), 2)

    ahora_dt = obtener_ahora_local()
    # Recibe la fecha y hora completa enviada por el navegador o toma la del servidor
    fecha_completa = payload.get(
        "fecha_hora", ahora_dt.strftime(FORMATO_FECHA_HORA)
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
            "monto_original": monto,
            "metodo": metodo,
            "cliente": cliente,
            "descripcion": descripcion,
            "fecha": fecha_completa,
            "cobrado": True if metodo == "Yape" else False,
            "metodo_cobro": "Yape" if metodo == "Yape" else None,
            "abonos": [],
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
            "fecha": fecha_completa,
            "eliminado": False,
        }

    datos.append(nuevo_registro)
    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/editar", methods=["POST"])
def editar_registro():
    payload = request.json
    registro_id = int(payload.get("id"))
    nuevo_monto = round(float(payload.get("monto", 0)), 2)
    nuevo_dueno = payload.get("dueno")
    nuevo_detalle = payload.get("detalle", "").strip()
    nueva_desc = payload.get("descripcion", "").strip()

    datos = cargar_datos()
    for d in datos:
        if d.get("id") == registro_id:
            d["monto"] = nuevo_monto
            if "monto_original" in d:
                d["monto_original"] = nuevo_monto
            d["dueno"] = nuevo_dueno
            if d.get("tipo") == "Ingreso":
                d["cliente"] = nuevo_detalle
                d["descripcion"] = nueva_desc
            else:
                d["motivo"] = nuevo_detalle
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/cobrar_fiado", methods=["POST"])
def cobrar_fiado():
    payload = request.json
    fiado_id = int(payload.get("id"))
    metodo_cobro = payload.get("metodo_cobro", "Yape")
    ahora_local = payload.get(
        "fecha_hora", obtener_ahora_local().strftime(FORMATO_FECHA_HORA)
    )

    datos = cargar_datos()
    for d in datos:
        if d.get("id") == fiado_id:
            d["cobrado"] = True
            d["metodo_cobro"] = metodo_cobro
            d["fecha_cobro"] = ahora_local
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/abonar_fiado", methods=["POST"])
def abonar_fiado():
    payload = request.json
    fiado_id = int(payload.get("id"))
    monto_abono = round(float(payload.get("monto_abono", 0)), 2)
    metodo_cobro = payload.get("metodo_cobro", "Yape")

    ahora_dt = obtener_ahora_local()
    fecha_hora_local = payload.get(
        "fecha_hora", ahora_dt.strftime(FORMATO_FECHA_HORA)
    )

    datos = cargar_datos()
    fiado_obj = next((d for d in datos if d.get("id") == fiado_id), None)

    if fiado_obj and monto_abono > 0:
        if "abonos" not in fiado_obj or not isinstance(
            fiado_obj["abonos"], list
        ):
            fiado_obj["abonos"] = []

        nuevo_id = max([d.get("id", 0) for d in datos], default=0) + 1

        if monto_abono >= fiado_obj["monto"]:
            monto_real_abonado = fiado_obj["monto"]
            fiado_obj["abonos"].append(
                {
                    "abono_id": nuevo_id,
                    "monto": monto_real_abonado,
                    "metodo": metodo_cobro,
                    "fecha": fecha_hora_local,
                }
            )
            fiado_obj["monto"] = 0.0
            fiado_obj["cobrado"] = True
            fiado_obj["metodo_cobro"] = metodo_cobro
            fiado_obj["fecha_cobro"] = fecha_hora_local
        else:
            monto_real_abonado = monto_abono
            fiado_obj["abonos"].append(
                {
                    "abono_id": nuevo_id,
                    "monto": monto_real_abonado,
                    "metodo": metodo_cobro,
                    "fecha": fecha_hora_local,
                }
            )
            fiado_obj["monto"] = round(
                fiado_obj["monto"] - monto_real_abonado, 2
            )

        registro_abono = {
            "id": nuevo_id,
            "fiado_origen_id": fiado_id,
            "tipo": "Ingreso",
            "dueno": fiado_obj["dueno"],
            "monto": monto_real_abonado,
            "metodo": metodo_cobro,
            "cliente": fiado_obj.get("cliente", ""),
            "descripcion": f"Abono a fiado #{fiado_id} ({fiado_obj.get('descripcion', '')})",
            "fecha": fecha_hora_local,
            "cobrado": True,
            "metodo_cobro": metodo_cobro,
            "eliminado": False,
        }
        datos.append(registro_abono)

        guardar_datos(datos)
        return jsonify({"status": "ok"})

    return jsonify({"status": "error", "mensaje": "Monto de abono inválido"})


@app.route("/api/eliminar_abono_especifico", methods=["POST"])
def eliminar_abono_especifico():
    payload = request.json
    fiado_id = int(payload.get("fiado_id"))
    abono_id = int(payload.get("abono_id"))

    datos = cargar_datos()
    fiado_obj = next((d for d in datos if d.get("id") == fiado_id), None)
    registro_abono = next((d for d in datos if d.get("id") == abono_id), None)

    if fiado_obj and registro_abono:
        monto_devuelto = registro_abono.get("monto", 0)

        fiado_obj["monto"] = round(fiado_obj["monto"] + monto_devuelto, 2)
        fiado_obj["cobrado"] = False
        fiado_obj["fecha_cobro"] = None

        if "abonos" in fiado_obj:
            fiado_obj["abonos"] = [
                ab
                for ab in fiado_obj["abonos"]
                if ab.get("abono_id") != abono_id
            ]

        registro_abono["eliminado"] = True
        registro_abono["fecha_eliminado"] = obtener_ahora_local().strftime(
            FORMATO_FECHA_HORA
        )

        guardar_datos(datos)
        return jsonify({"status": "ok"})

    return jsonify(
        {"status": "error", "mensaje": "Registro de abono no encontrado"}
    )


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
            if d.get("monto", 0) == 0 and "monto_original" in d:
                d["monto"] = d["monto_original"]
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/eliminar", methods=["POST"])
def eliminar_registro():
    payload = request.json
    registro_id = int(payload.get("id"))
    ahora_local = obtener_ahora_local().strftime(FORMATO_FECHA_HORA)
    datos = cargar_datos()

    for d in datos:
        if d.get("id") == registro_id:
            d["eliminado"] = True
            d["fecha_eliminado"] = ahora_local
            break

    guardar_datos(datos)
    return jsonify({"status": "ok"})


@app.route("/api/restaurar", methods=["POST"])
def restaurar_registro():
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


@app.route("/api/backup_json", methods=["GET"])
def backup_json():
    datos = cargar_datos()
    fecha_hoy = obtener_ahora_local().strftime(FORMATO_FECHA)
    salida = json.dumps(datos, indent=4, ensure_ascii=False)
    return Response(
        salida,
        mimetype="application/json",
        headers={
            "Content-Disposition": f"attachment;filename=backup_caja_{fecha_hoy}.json"
        },
    )


@app.route("/api/exportar_csv", methods=["GET"])
def exportar_csv():
    ahora_str = obtener_ahora_local().strftime(FORMATO_FECHA)
    desde = request.args.get("desde", ahora_str)
    hasta = request.args.get("hasta", ahora_str)

    datos = cargar_datos()
    salida = io.StringIO()
    salida.write("\ufeff")

    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(
        [
            "ID",
            "Fecha y Hora",
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
            continue

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
                    d.get("fecha", ""),
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