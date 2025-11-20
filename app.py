import os
import io
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject

app = Flask(__name__)

# -------------------------------------------------------
# CONFIGURACIÓN DE PLANTILLAS PDF
# Los nombres deben coincidir con los archivos en Render
# -------------------------------------------------------
PDF_TEMPLATES = {
    "doctorado": "Contrato_Doctorado.pdf",
    "maestria": "Contrato_Maestria.pdf",
    "licenciatura": "Contrato_Licenciatura.pdf",
    "masterpropio": "Contrato_MasterPropio.pdf",  # tipo_contrato = "masterpropio"
}

# -------------------------------------------------------
# MAPEO JSON -> CAMPOS DEL FORMULARIO PDF
# Ajusta estos nombres si los campos internos del PDF
# tienen nombres diferentes.
# -------------------------------------------------------
JSON_TO_PDF_FIELDS = {
    "titulacion": "TITULACION",
    "nombre_apellidos": "NOMBRE_APELLIDOS",
    "documento_id": "DOCUMENTO_ID",
    "telefono_fijo": "TELEFONO_FIJO",
    "fecha_nacimiento": "FECHA_NACIMIENTO",
    "nacionalidad": "NACIONALIDAD",
    "email": "EMAIL",
    "telefono_movil": "TELEFONO_MOVIL",
    "direccion": "DIRECCION",
    "ciudad": "CIUDAD",
    "provincia": "PROVINCIA",  # nombre principal para provincia
    "pais": "PAIS",

    # Campos extra:
    # FECHA del día (dd/mm/aaaa)
    "fecha_actual": "FECHA",
    # FECHA DE INICIO fija
    "fecha_inicio_fija": "FECHA_INICIO",
    # NOMBRE DEL PROGRAMA
    "nombre_programa": "NOMBRE_PROGRAMA",
}


def sanitize_filename(text: str, default: str = "Contrato") -> str:
    """
    Limpia el nombre del archivo final (quita caracteres raros).
    """
    if not text:
        text = default
    text = text.strip().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    sanitized = "".join(ch for ch in text if ch in allowed)
    return sanitized or default


def fill_pdf(template_path: str, field_values: dict) -> bytes:
    """
    Carga una plantilla PDF, rellena los campos de formulario (AcroForm)
    y devuelve el PDF resultante en bytes.
    """
    reader = PdfReader(template_path)
    writer = PdfWriter()

    # Copiar todas las páginas
    writer.append_pages_from_reader(reader)

    # Copiar el diccionario AcroForm (si existe) y activar NeedAppearances
    root = writer._root_object
    if "/AcroForm" in reader.trailer["/Root"]:
        root.update({NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]})
        # Necesario para que muchos lectores PDF muestren los valores
        root["/AcroForm"].update(
            {NameObject("/NeedAppearances"): BooleanObject(True)}
        )

    # Rellenar los campos en cada página
    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values)

    # Escribir a memoria
    output_stream = io.BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)
    return output_stream.getvalue()


@app.route("/")
def home():
    return (
        "API CESUMA lista para generar contratos PDF. "
        "Endpoint principal: POST /llenar_pdf"
    )


@app.route("/listar_campos", methods=["GET"])
def listar_campos():
    """
    Endpoint opcional para depurar.
    Devuelve la lista de campos del formulario PDF para un tipo_contrato.

    Ejemplo:
      GET /listar_campos?tipo_contrato=doctorado
    """
    tipo = request.args.get("tipo_contrato", "doctorado").strip().lower()
    if tipo not in PDF_TEMPLATES:
        return jsonify(
            {
                "error": "tipo_contrato no válido",
                "permitidos": list(PDF_TEMPLATES.keys()),
            }
        ), 400

    template_filename = PDF_TEMPLATES[tipo]
    template_path = os.path.join(os.path.dirname(__file__), template_filename)

    if not os.path.exists(template_path):
        return jsonify(
            {
                "error": "No se encontró la plantilla PDF",
                "plantilla_esperada": template_filename,
                "tipo_contrato": tipo,
            }
        ), 500

    try:
        reader = PdfReader(template_path)
        fields = reader.get_fields()

        if not fields:
            return jsonify(
                {
                    "mensaje": "No se detectaron campos de formulario (AcroForm) en el PDF.",
                    "tipo_contrato": tipo,
                    "plantilla": template_filename,
                }
            ), 200

        campos = {}
        for name, field in fields.items():
            campos[name] = {
                "type": str(field.get("/FT", "")),
                "value": str(field.get("/V", "")),
                "alt_name": str(field.get("/T", name)),
            }

        return jsonify(
            {
                "tipo_contrato": tipo,
                "plantilla": template_filename,
                "campos": campos,
            }
        ), 200

    except Exception as e:
        return jsonify({"error": "Error leyendo campos del PDF", "detalle": str(e)}), 500


@app.route("/llenar_pdf", methods=["POST"])
def llenar_pdf():
    """
    Endpoint principal:

    1) Recibe JSON con:
       tipo_contrato, titulacion, nombre_apellidos, documento_id,
       telefono_fijo, fecha_nacimiento, nacionalidad, email,
       telefono_movil, direccion, ciudad, provincia, pais, nombre_programa.

    2) Calcula:
       - fecha_actual (dd/mm/aaaa del día)
       - fecha_inicio_fija = 10-Dic-2025

    3) Rellena el PDF correspondiente.

    4) Devuelve el PDF generado.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Se requiere un JSON válido"}), 400

    # 1. Validar tipo_contrato
    tipo_contrato = data.get("tipo_contrato")
    if not tipo_contrato:
        return jsonify({"error": "Falta el campo tipo_contrato"}), 400

    tipo_contrato = str(tipo_contrato).strip().lower()
    if tipo_contrato not in PDF_TEMPLATES:
        return jsonify(
            {
                "error": "tipo_contrato no válido",
                "permitidos": list(PDF_TEMPLATES.keys()),
            }
        ), 400

    # 2. Buscar plantilla
    template_filename = PDF_TEMPLATES[tipo_contrato]
    template_path = os.path.join(os.path.dirname(__file__), template_filename)
    if not os.path.exists(template_path):
        return jsonify(
            {
                "error": "No se encontró la plantilla PDF para el tipo de contrato",
                "plantilla_esperada": template_filename,
                "tipo_contrato": tipo_contrato,
            }
        ), 500

    # 3. Enriquecer datos
    enriched = dict(data)
    # Fecha actual en formato dd/mm/aaaa
    enriched["fecha_actual"] = datetime.now().strftime("%d/%m/%Y")
    # Fecha de inicio fija
    enriched["fecha_inicio_fija"] = "10-Dic-2025"
    # Nombre del programa por si no viene
    if "nombre_programa" not in enriched:
        enriched["nombre_programa"] = ""

    # 4. Construir diccionario de campos para el PDF
    pdf_fields = {}
    for json_key, pdf_field_name in JSON_TO_PDF_FIELDS.items():
        value = enriched.get(json_key, "")
        pdf_fields[pdf_field_name] = str(value)

    # Extra: duplicar provincia al campo "PROVINCIA / ESTADO / DEPARTAMENTO"
    if "PROVINCIA" in pdf_fields:
        pdf_fields["PROVINCIA / ESTADO / DEPARTAMENTO"] = pdf_fields["PROVINCIA"]

    try:
        # 5. Rellenar el PDF
        pdf_bytes = fill_pdf(template_path, pdf_fields)

        # 6. Nombre del archivo final
        nombre_estudiante = enriched.get("nombre_apellidos", "Contrato")
        nombre_estudiante = sanitize_filename(nombre_estudiante)
        filename = f"Contrato_{tipo_contrato}_{nombre_estudiante}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({"error": "Error generando PDF", "detalle": str(e)}), 500


if __name__ == "__main__":
    # Para local: python app.py
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
