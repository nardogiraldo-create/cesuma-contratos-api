import os
import io
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject

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

# -------------------------------------------------------
# MAPEO JSON -> CAMPOS PDF
# (ajusta estos nombres si los campos internos del PDF son otros)
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
    "provincia": "PROVINCIA",  # campo principal de provincia
    "pais": "PAIS",

    # Campo fecha actual (día de generación del contrato)
    "fecha_actual": "FECHA",           # dd/mm/aaaa
    # Campo fecha de inicio fija
    "fecha_inicio_fija": "FECHA_INICIO",  # 10-Dic-2025
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
    1) Recibe JSON desde Apps Script
    2) Enriquece con fechas (actual + fija)
    3) Abre plantilla
    4) Llena los campos de formulario
    5) Devuelve PDF descargable
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Se requiere un JSON válido"}), 400

    # -----------------------------------
    # 1. Validar tipo_contrato
    # -----------------------------------
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

    # -----------------------------------
    # 2. Ruta de plantilla
    # -----------------------------------
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

    # -----------------------------------
    # 3. Enriquecer data con fechas automáticas
    # -----------------------------------
    enriched = dict(data)

    # Fecha actual: día/mes/año
    enriched["fecha_actual"] = datetime.now().strftime("%d/%m/%Y")
    # Fecha inicio fija
    enriched["fecha_inicio_fija"] = "10-Dic-2025"
    # Nombre del programa por si no llega
    if "nombre_programa" not in enriched:
        enriched["nombre_programa"] = ""

    try:
        # -----------------------------------
        # 4. Leer PDF y copiar páginas + AcroForm
        # -----------------------------------
        reader = PdfReader(template_path)
        writer = PdfWriter()

        # Copiar todas las páginas
        writer.append_pages_from_reader(reader)

        # Copiar /AcroForm (formulario)
        if "/AcroForm" in reader.trailer["/Root"]:
            writer._root_object.update(
                {NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]}
            )
            # Forzar NeedAppearances para que se vean los valores
            writer._root_object["/AcroForm"].update(
                {NameObject("/NeedAppearances"): BooleanObject(True)}
            )

        # -----------------------------------
        # 5. Construir diccionario de valores para campos
        # -----------------------------------
        pdf_field_values = {}
        for json_key, pdf_field in JSON_TO_PDF_FIELDS.items():
            value = enriched.get(json_key, "")
            pdf_field_values[pdf_field] = str(value)

        # Truco: duplicar valor de PROVINCIA a campo alternativo
        if "PROVINCIA" in pdf_field_values:
            pdf_field_values["PROVINCIA / ESTADO / DEPARTAMENTO"] = pdf_field_values["PROVINCIA"]

        # -----------------------------------
        # 6. Rellenar los campos en cada página
        # -----------------------------------
        for page in writer.pages:
            writer.update_page_form_field_values(page, pdf_field_values)

        # -----------------------------------
        # 7. Escribir PDF a memoria
        # -----------------------------------
        pdf_bytes = io.BytesIO()
        writer.write(pdf_bytes)
        pdf_bytes.seek(0)

        # -----------------------------------
        # 8. Nombre del archivo final
        # -----------------------------------
        nombre_estudiante = enriched.get("nombre_apellidos", "Contrato")
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
