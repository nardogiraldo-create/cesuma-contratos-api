import os
import io
from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

# -------------------------------------------------------
# CONFIGURACIÓN DE PLANTILLAS
# -------------------------------------------------------
# Mapeo entre tipo_contrato (valor que llega en el JSON)
# y el nombre del archivo PDF de plantilla en el repositorio.
PDF_TEMPLATES = {
    "doctorado": "Contrato_Doctorado.pdf",
    "maestria": "Contrato_Maestria.pdf",
    "licenciatura": "Contrato_Licenciatura.pdf",
    "master_propio": "Contrato_MasterPropio.pdf",
}

# Mapeo entre claves JSON y nombres de campos en el PDF
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
    "provincia": "PROVINCIA",
    "pais": "PAIS",
}


def sanitize_filename(text: str, default: str = "Contrato") -> str:
    """
    Limpia el nombre de archivo para evitar caracteres raros.
    """
    if not text:
        text = default

    # Reemplaza espacios por guiones bajos
    text = text.strip().replace(" ", "_")

    # Deja solo letras, números, guiones y guiones bajos
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    sanitized = "".join(ch for ch in text if ch in allowed)

    return sanitized or default


# -------------------------------------------------------
# RUTA DE PRUEBA (GET /)
# -------------------------------------------------------
@app.route("/")
def home():
    return "API CESUMA lista para generar contratos PDF (endpoint /llenar_pdf activo) 😎"


# -------------------------------------------------------
# ENDPOINT PRINCIPAL: POST /llenar_pdf
# -------------------------------------------------------
@app.route("/llenar_pdf", methods=["POST"])
def llenar_pdf():
    """
    1) Recibe JSON con los datos del contrato.
    2) Elige la plantilla según tipo_contrato.
    3) Rellena la plantilla PDF con los datos.
    4) Devuelve el PDF generado como archivo descargable.
    """

    # 1. Validar que el cuerpo sea JSON
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Se requiere un cuerpo JSON válido"}), 400

    # 2. Leer y validar tipo_contrato
    tipo_contrato = data.get("tipo_contrato")
    if not tipo_contrato:
        return jsonify({"error": "Falta el campo 'tipo_contrato' en el JSON"}), 400

    tipo_contrato = str(tipo_contrato).strip().lower()
    if tipo_contrato not in PDF_TEMPLATES:
        return jsonify(
            {
                "error": "tipo_contrato no válido",
                "detalle": f"Debe ser uno de: {', '.join(PDF_TEMPLATES.keys())}",
            }
        ), 400

    # 3. Obtener la ruta de la plantilla
    template_filename = PDF_TEMPLATES[tipo_contrato]
    template_path = os.path.join(os.path.dirname(__file__), template_filename)

    if not os.path.exists(template_path):
        return jsonify(
            {
                "error": "No se encontró la plantilla PDF para el tipo de contrato",
                "tipo_contrato": tipo_contrato,
                "plantilla_esperada": template_filename,
            }
        ), 500

    try:
        # 4. Leer la plantilla PDF
        reader = PdfReader(template_path)
        writer = PdfWriter()

        # Copiar todas las páginas
        for page in reader.pages:
            writer.add_page(page)

        # 5. Construir diccionario de valores para los campos PDF
        pdf_field_values = {}
        for json_key, pdf_field in JSON_TO_PDF_FIELDS.items():
            value = data.get(json_key, "")
            if value is None:
                value = ""
            pdf_field_values[pdf_field] = str(value)

        # 6. Actualizar los campos en cada página
        for page in writer.pages:
            writer.update_page_form_field_values(page, pdf_field_values)

        # 7. Escribir el PDF resultante en memoria
        output_pdf_stream = io.BytesIO()
        writer.write(output_pdf_stream)
        output_pdf_stream.seek(0)

        # 8. Definir nombre del archivo final
        nombre_estudiante = data.get("nombre_apellidos", "") or "Contrato"
        nombre_estudiante_sanitizado = sanitize_filename(nombre_estudiante)
        filename = f"Contrato_{tipo_contrato}_{nombre_estudiante_sanitizado}.pdf"

        # 9. Devolver el PDF como archivo adjunto
        return send_file(
            output_pdf_stream,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        # Manejo genérico de errores
        return jsonify({"error": "Error al generar el PDF", "detalle": str(e)}), 500


# -------------------------------------------------------
# MAIN (para pruebas locales, Render usa gunicorn)
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
