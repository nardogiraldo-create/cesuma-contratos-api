import os
import io
from datetime import datetime

from flask import Flask, request, jsonify, send_file
# Asegúrate de que tienes pypdf instalado: pip install pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject

app = Flask(__name__)

# -------------------------------------------------------
# CONFIGURACIÓN DE PLANTILLAS PDF
# -------------------------------------------------------
PDF_TEMPLATES = {
    "doctorado": "Contrato_Doctorado.pdf",
    "maestria": "Contrato_Maestria.pdf",
    "licenciatura": "Contrato_Licenciatura.pdf",
    "masterpropio": "Contrato_MasterPropio.pdf", 
}

# -------------------------------------------------------
# DATOS DE PRECIO FIJOS SEGÚN EL TIPO DE CONTRATO
# -------------------------------------------------------
FIXED_PRICING = {
    "doctorado": {
        "total": "$70,200 MXN",
        "matricula": "$ 2,925 MXN",
        "tipo_pago": "Fraccionado",
        "num_cuotas": "23",
        "importe_cuota": "$2,925 MXN",
    },
    "maestria": {
        "total": "$52,800.00 MXN",
        "matricula": "$2,640.00 MXN",
        "tipo_pago": "FRACCIONADO",
        "num_cuotas": "19",
        "importe_cuota": "$2,640.00 MXN",
    },
}

# -------------------------------------------------------
# MAPEO JSON -> CAMPOS DEL FORMULARIO PDF
# -------------------------------------------------------
JSON_TO_PDF_FIELDS = {
    # DATOS DEL PROGRAMA
    "nombre_programa": "Nombre del programa", 
    "titulacion": "Titulaci\u00f3n acad\u00e9mica", 
    
    # DATOS DEL ALUMNO/A
    "nombre_apellidos": "Nombre y Apellidos",
    "documento_id": "Documento Identidad",
    "telefono_fijo": "Tel\u00e9fono fijo",
    "fecha_nacimiento": "Fecha de Nacimiento",
    "nacionalidad": "Nacionalidad",
    "email": "Email",
    "telefono_movil": "Tel\u00e9fono m\u00f3vil",
    "ocupacion_actual": "Ocupaci\u00f3n actual", 
    
    # LUGAR DE RESIDENCIA
    "direccion": "Direcci\u00f3n",
    "ciudad": "Poblaci\u00f3n / Ciudad", 
    "provincia": "Provincia / Estado / Departamento", 
    "pais": "Pa\u00eds", 

    # Campos de Precio Fijo
    "total": "Total",
    "matricula": "Matr\u00edcula",
    "tipo_pago": "Tipo de pago",
    "num_cuotas": "Cuotas", 
    "importe_cuota": "Importe",
    
    # Campos extra
    "fecha_actual": "fecha_original", 
    "fecha_inicio_fija": "Fecha de inicio_af_date", 
}


def sanitize_filename(text: str, default: str = "Contrato") -> str:
    if not text:
        text = default
    text = text.strip().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    sanitized = "".join(ch for ch in text if ch in allowed)
    return sanitized or default


def fill_pdf(template_path: str, field_values: dict) -> bytes:
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    root = writer._root_object
    if "/AcroForm" in reader.trailer["/Root"]:
        root.update({NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]})
        root["/AcroForm"].update(
            {NameObject("/NeedAppearances"): BooleanObject(True)}
        )
    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values)
    output_stream = io.BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)
    return output_stream.getvalue()


@app.route("/")
def home():
    return "API CESUMA Activa."


@app.route("/listar_campos", methods=["GET"])
def listar_campos():
    tipo = request.args.get("tipo_contrato", "doctorado").strip().lower()
    if tipo not in PDF_TEMPLATES:
        return jsonify({"error": "tipo invalido"}), 400
    template_path = os.path.join(os.path.dirname(__file__), PDF_TEMPLATES[tipo])
    try:
        reader = PdfReader(template_path)
        fields = reader.get_fields()
        campos = {}
        if fields:
            for name, field in fields.items():
                campos[name] = {"type": str(field.get("/FT", "")), "value": str(field.get("/V", "")), "alt_name": str(field.get("/T", name))}
        return jsonify({"tipo_contrato": tipo, "plantilla": PDF_TEMPLATES[tipo], "campos": campos}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/llenar_pdf", methods=["POST"])
def llenar_pdf():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON requerido"}), 400

    tipo_contrato = str(data.get("tipo_contrato", "")).strip().lower()
    if tipo_contrato not in PDF_TEMPLATES:
        return jsonify({"error": "Tipo de contrato no válido"}), 400

    template_path = os.path.join(os.path.dirname(__file__), PDF_TEMPLATES[tipo_contrato])
    if not os.path.exists(template_path):
        return jsonify({"error": "Plantilla no encontrada"}), 500

    enriched = dict(data)
    
    # ===========================================================
    # APLICANDO TUS CORRECCIONES SOLICITADAS
    # ===========================================================
    
    # 1. PAIS AUTOMÁTICO: Siempre será Colombia
    enriched["pais"] = "Colombia"
    
    # 2. TELÉFONO FIJO = TELÉFONO MÓVIL
    # Tomamos lo que venga en el móvil y lo ponemos en el fijo
    telefono_movil_valor = enriched.get("telefono_movil", "")
    enriched["telefono_fijo"] = telefono_movil_valor
    
    # 3. Valores Fijos existentes
    enriched["ocupacion_actual"] = "Trabajador" 
    enriched["fecha_actual"] = datetime.now().strftime("%d/%m/%Y")
    enriched["fecha_inicio_fija"] = "10-Dic-2025" 

    # 4. Precios fijos según contrato
    pricing = FIXED_PRICING.get(tipo_contrato, {})
    if pricing:
        enriched.update(pricing)
    
    # 5. Asegurar claves vacías si no llegan (para evitar errores en el mapeo)
    # Nota: pais y telefono_fijo ya están cubiertos arriba
    for key in ["nombre_programa", "provincia", "ciudad"]:
        if key not in enriched or enriched[key] is None:
            enriched[key] = ""
        
    # Construcción del diccionario final para el PDF
    pdf_fields = {}
    for json_key, pdf_field_name in JSON_TO_PDF_FIELDS.items():
        value = enriched.get(json_key, "")
        pdf_fields[pdf_field_name] = str(value)

    try:
        pdf_bytes = fill_pdf(template_path, pdf_fields)
        safe_name = sanitize_filename(enriched.get("nombre_apellidos", "Contrato"))
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Contrato_{tipo_contrato}_{safe_name}.pdf",
        )
    except Exception as e:
        return jsonify({"error": "Error generando PDF", "detalle": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
