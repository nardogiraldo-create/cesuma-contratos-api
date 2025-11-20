import os
import io
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

# -------------------------------------------------------
# CONFIGURACIÓN DE PLANTILLAS
# -------------------------------------------------------
PDF_TEMPLATES = {
    "doctorado": "Contrato_Doctorado.pdf",
    "maestria": "Contrato_Maestria.pdf",
    "licenciatura": "Contrato_Licenciatura.pdf",
    "masterpropio": "Contrato_MasterPropio.pdf",  # tipo_contrato = "masterpropio"
}

# Mapeo entre claves JSON y nombres de campos en el PDF
# (agregamos fecha_actual, fecha_inicio_fija y nombre_programa)
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
    "provincia": "PROVINCIA",             # campo principal
    "pais": "PAIS",

    # NUEVOS CAMPOS:
    # Fecha del día en que se genera el contrato (dd/mm/aaaa)
    "fecha_actual": "FECHA",
    # Fecha de inicio fija
    "fecha_inicio_fija": "FECHA_INICIO",
    # Nombre del programa
    "nombre_programa": "NOMBRE_PROGRAMA",
}


def sanitize_filename(text: str, default: str = "Contrato") -> str:
    """Limpia caracteres raros del nombre de archivo."""
    if not text:
        text = default
    text = text.strip().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    sanitized = "".join(ch for ch in text if ch in allowed)
    return sanitized or default


@app.route("/")
def home():
    return "API CESUMA lista para generar contratos PDF (endpoint /llenar_pdf activo) 😎"


@app.route("/llenar_pdf", methods=["POST"])
def llenar_pdf():
    """
    1) Recibe JSON
    2) Enriquece con campos automáticos (fecha_actual, fecha_inicio_fija)
    3) Selecciona una plantilla
    4) Llena los campos
    5) Devuelve PDF descargable
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Se requiere un JSON válido"}), 400

    # ------------------------------
    # 1. Validar tipo_contrato
    # ------------------------------
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

    # ------------------------------
    # 2. Ruta de la plantilla
    # ------------------------------
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

    # ------------------------------
    # 3. Enriquecer datos con fechas automáticas
    # ------------------------------
    enriched_data = dict(data)  # copia del JSON original

    # Fecha de hoy en formato dd/mm/aaaa
    today_str = datetime.now().strftime("%d/%m/%Y")
    enriched_data["fecha_actual"] = today_str

    # Fecha de inicio fija
    enriched_data["fecha_inicio_fija"] = "10-Dic-2025"

    # Si no viene nombre_programa en el JSON, que al menos no truene
    if "nombre_programa" not in enriched_data:
        enriched_data["nombre_programa"] = ""

    try:
        # ------------------------------
        # 4. Leer la plantilla y clonar
        # ------------------------------
        reader = PdfReader(template_path)

        writer = PdfWriter()
        writer.clone_reader_document_root(reader)

        # ------------------------------
        # 5. Construir diccionario de valores
        # ------------------------------
        pdf_field_values = {}
        for json_key, pdf_field in JSON_TO_PDF_FIELDS.items():
            value = enriched_data.get(json_key, "")
            pdf_field_values[pdf_field] = str(value)

        # Truco extra: si el campo de provincia en el PDF
        # se llamara "PROVINCIA / ESTADO / DEPARTAMENTO",
        # también lo rellenamos con el mismo valor.
        if "PROVINCIA" in pdf_field_values:
            pdf_field_values["PROVINCIA / ESTADO / DEPARTAMENTO"] = pdf_field_values["PROVINCIA"]

        # ------------------------------
        # 6. Rellenar los campos en todas las páginas
        # ------------------------------
        for page in writer.pages:
            writer.update_page_form_field_values(page, pdf_field_values)

        # ------------------------------
        # 7. Escribir a memoria
        # ------------------------------
        pdf_bytes = io.BytesIO()
        writer.write(pdf_bytes)
        pdf_bytes.seek(0)

        # ------------------------------
        # 8. Nombre del archivo final
        # ------------------------------
        nombre_estudiante = enriched_data.get("nombre_apellidos", "Contrato")
        nombre_estudiante = sanitize_filename(nombre_estudiante)
        filename = f"Contrato_{tipo_contrato}_{nombre_estudiante}.pdf"

        return send_file(
            pdf_bytes,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({"error": "Error generando PDF", "detalle": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
