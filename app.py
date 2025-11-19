import os
import io
from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject  # 👈 IMPORTANTE

app = Flask(__name__)

# -------------------------------------------------------
# CONFIGURACIÓN DE PLANTILLAS
# -------------------------------------------------------
PDF_TEMPLATES = {
    "doctorado": "Contrato_Doctorado.pdf",
    "maestria": "Contrato_Maestria.pdf",
    "licenciatura": "Contrato_Licenciatura.pdf",
    "masterpropio": "Contrato_MasterPropio.pdf",
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
    2) Selecciona una plantilla
    3) Llena los campos
    4) Devuelve PDF descargable
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Se requiere un JSON válido"}), 400

    # Validar tipo_contrato
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

    # Ruta plantilla
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

    try:
        # 1) Leer la plantilla
        reader = PdfReader(template_path)

        # 2) Clonar TODO el documento (páginas + AcroForm + estructura)
        writer = PdfWriter()
        writer.clone_reader_document_root(reader)

        # 3) Obtener campos del PDF y mapear dinámicamente
        #    Ejemplo: "NOMBRE_APELLIDOS" -> JSON key "nombre_apellidos"
        fields = reader.get_fields() or {}
        pdf_field_values = {}

        for pdf_field_name in fields.keys():
            json_key = pdf_field_name.lower()  # TITULACION -> titulacion
            value = data.get(json_key, "")
            pdf_field_values[pdf_field_name] = str(value)

        # 4) Rellenar los campos en todas las páginas
        for page in writer.pages:
            writer.update_page_form_field_values(page, pdf_field_values)

        # 5) Forzar que se vean los valores en los visores (NeedAppearances)
        if "/AcroForm" in writer._root_object:
            writer._root_object["/AcroForm"].update(
                {NameObject("/NeedAppearances"): BooleanObject(True)}
            )

        # 6) Salida PDF a memoria
        pdf_bytes = io.BytesIO()
        writer.write(pdf_bytes)
        pdf_bytes.seek(0)

        # 7) Nombre del archivo final
        nombre_estudiante = data.get("nombre_apellidos", "Contrato")
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
