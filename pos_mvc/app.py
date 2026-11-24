import io
import json
from datetime import datetime
import pandas as pd
import requests
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

app = Flask(__name__)
app.secret_key = "secreto_super_seguro_pos"

app.json.ensure_ascii = False

API_URL = "http://127.0.0.1:8000/api"


# --- RUTA DE LOGIN ---

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Validación en Backend
        if not username or not password:
            return render_template("login.html", error="Por favor completa todos los campos")

        try:
            response = requests.post(f"{API_URL}/auth/login", json={"username": username, "password": password})
            if response.status_code == 200:
                user_data = response.json()["usuario"]
                session["usuario"] = user_data

                rol = str(user_data.get("rol", "")).upper()

                if "ADMIN" in rol:
                    return redirect(url_for("administrador"))
                elif "ALMACEN" in rol:
                    return redirect(url_for("almacenista"))
                elif "VENDEDOR" in rol:
                    return redirect(url_for("vendedor"))
                else:
                    return render_template("login.html", error=f"Rol no reconocido: {rol}")
            else:
                return render_template("login.html", error="Credenciales inválidas")
        except requests.exceptions.RequestException:
            return render_template("login.html", error="Error de conexión con la API")

    return render_template("login.html", error=None)


# --- RUTA VENDEDOR ---

# --- RUTA VENDEDOR ---

@app.route('/vendedor', methods=['GET', 'POST'])
def vendedor():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == 'POST':
        # --- PROCESAR VENTA ---

        # --- PROCESAR VENTA ---
        if 'venta' in request.form:
            nombre_cliente = request.form.get('nombre_cliente', 'Cliente General')
            productos_raw = request.form.get('productos')

            try:
                lista_productos = json.loads(productos_raw) if productos_raw else []
                
                payload = {
                    "cliente": nombre_cliente,
                    "id_usuario": session.get("usuario", {}).get("id_usuario", 1),
                    "productos": lista_productos
                }

                res = requests.post(f"{API_URL}/ventas", json=payload)
                print(f"[DEBUG VENTA] Status Code: {res.status_code} | Respuesta: {res.text}")

                if res.status_code in [200, 201]:
                    flash("Venta registrada con éxito", "success")
                    return redirect(url_for('historial_ventas_route'))
                else:
                    try:
                        error_detail = res.json().get('detail', res.text)
                    except Exception:
                        error_detail = res.text
                    flash(f"Error en API (500): {error_detail}", "danger")

            except json.JSONDecodeError:
                flash("El formato de productos no es un JSON válido.", "danger")
            except requests.exceptions.RequestException as e:
                print(f"[ERROR CONEXION API]: {e}")
                flash("No se pudo conectar con la API backend", "danger")

        # --- PROCESAR DEVOLUCIÓN ---
        elif 'devolucion' in request.form:
            try:
                data_dev = {
                    "id_venta": int(request.form.get("id_venta")),
                    "id_producto": int(request.form.get("id_producto")),
                    "cantidad": int(request.form.get("cantidad")),
                    "motivo": request.form.get("motivo", "")
                }
                
                res = requests.post(f"{API_URL}/ventas/devolucion", json=data_dev)
                
                if res.status_code in [200, 201]:
                    flash("Devolución registrada con éxito", "success")
                else:
                    flash(f"Error al procesar devolución: {res.text}", "danger")
            except Exception as e:
                flash(f"Error en los datos de devolución: {e}", "danger")
        
    return render_template('vendedor.html')

# --- RUTA ALMACENISTA ---

@app.route("/almacenista", methods=["GET", "POST"])
def almacenista():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            id_producto = int(request.form.get("id_producto"))
            tipo_movimiento = request.form.get("tipo_movimiento")
            cantidad = int(request.form.get("cantidad"))
            motivo = request.form.get("motivo", "").strip()

            # Validación de Datos en Backend
            if cantidad <= 0:
                flash("La cantidad del movimiento debe ser mayor a cero", "error")
                return redirect(url_for("almacenista"))

            data = {
                "id_producto": id_producto,
                "tipo_movimiento": tipo_movimiento,
                "cantidad": cantidad,
                "id_usuario": session["usuario"]["id_usuario"],
                "motivo": motivo
            }
            requests.post(f"{API_URL}/almacen/movimiento", json=data)
        except (ValueError, TypeError):
            flash("Verifica que los datos numéricos sean válidos", "error")

    return render_template("almacenista.html")


# --- RUTA ADMINISTRADOR ---

@app.route("/administrador", methods=["GET", "POST"])
def administrador():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        codigo_barras = request.form.get("codigo_barras", "").strip()
        nombre = request.form.get("nombre", "").strip()
        id_proveedor = request.form.get("id_proveedor")

        # Validación de datos en backend antes de enviar a API
        try:
            precio_compra = float(request.form.get("precio_compra"))
            precio_venta = float(request.form.get("precio_venta"))
            stock_actual = int(request.form.get("stock_actual"))
            stock_minimo = int(request.form.get("stock_minimo"))

            if not nombre or precio_compra <= 0 or precio_venta <= 0 or stock_actual < 0:
                flash("Todos los precios deben ser positivos y el producto debe tener nombre", "error")
                return redirect(url_for("administrador"))

            data = {
                "codigo_barras": codigo_barras,
                "nombre": nombre,
                "precio_compra": precio_compra,
                "precio_venta": precio_venta,
                "stock_actual": stock_actual,
                "stock_minimo": stock_minimo,
                "id_proveedor": int(id_proveedor) if id_proveedor else None
            }
            requests.post(f"{API_URL}/admin/productos", json=data)
            return redirect(url_for("administrador"))
        except (ValueError, TypeError):
            flash("Formatos de precios o stock no válidos", "error")

    # 1. Obtener lista de productos desde la API
    try:
        res = requests.get(f"{API_URL}/admin/productos")
        if res.status_code == 200:
            prod_json = res.json()
            productos = prod_json.get("data", prod_json) if isinstance(prod_json, dict) else prod_json
        else:
            productos = []
    except requests.exceptions.RequestException:
        productos = []

    # 2. Obtener lista de proveedores desde la API
    try:
        res_prov = requests.get(f"{API_URL}/admin/proveedores")
        if res_prov.status_code == 200:
            prov_json = res_prov.json()
            proveedores = prov_json.get("data", prov_json) if isinstance(prov_json, dict) else prov_json
        else:
            print(f"[WARN] Error consultando proveedores. Status: {res_prov.status_code}")
            proveedores = []
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] No se pudo conectar con el endpoint de proveedores: {e}")
        proveedores = []

    # 3. Obtener historial de ventas
    try:
        res_hist = requests.get(f"{API_URL}/ventas/historial")
        if res_hist.status_code == 200:
            hist_json = res_hist.json()
            historial = hist_json.get("data", hist_json) if isinstance(hist_json, dict) else hist_json
        else:
            historial = []
    except requests.exceptions.RequestException:
        historial = []

    return render_template("administrador.html", productos=productos, proveedores=proveedores, historial=historial)


# --- RUTAS CRUD (UPDATE & DELETE) ---

@app.route("/administrador/producto/editar/<int:id_producto>", methods=["POST"])
def editar_producto(id_producto):
    if "usuario" not in session:
        return redirect(url_for("login"))

    try:
        nombre = request.form.get("nombre", "").strip()
        precio_compra = float(request.form.get("precio_compra"))
        precio_venta = float(request.form.get("precio_venta"))
        stock_actual = int(request.form.get("stock_actual"))

        # Validación Backend
        if not nombre or precio_compra <= 0 or precio_venta <= 0 or stock_actual < 0:
            flash("Datos de edición inválidos", "error")
            return redirect(url_for("administrador"))

        data = {
            "nombre": nombre,
            "precio_compra": precio_compra,
            "precio_venta": precio_venta,
            "stock_actual": stock_actual
        }

        # Petición a la API para actualizar el producto
        requests.put(f"{API_URL}/admin/productos/{id_producto}", json=data)
    except (ValueError, TypeError):
        flash("Error en los tipos de datos enviados", "error")

    return redirect(url_for("administrador"))


@app.route("/administrador/producto/eliminar/<int:id_producto>", methods=["POST"])
def eliminar_producto(id_producto):
    if "usuario" not in session:
        return redirect(url_for("login"))

    try:
        requests.delete(f"{API_URL}/admin/productos/{id_producto}")
    except requests.exceptions.RequestException:
        flash("Error al conectar con la API para eliminar", "error")

    return redirect(url_for("administrador"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- EXPOSICIÓN DE ENDPOINTS / API REST ---

@app.route('/api/productos', methods=['GET'])
def api_obtener_productos():
    try:
        res = requests.get(f"{API_URL}/admin/productos")
        if res.status_code == 200:
            productos = res.json()
            return jsonify({
                "status": "success",
                "total": len(productos) if isinstance(productos, list) else 0,
                "data": productos
            }), 200
        else:
            return jsonify({"status": "error", "message": "No se pudieron obtener los productos"}), res.status_code
    except requests.exceptions.RequestException:
        return jsonify({"status": "error", "message": "Error de conexión con el backend de datos"}), 500


@app.route('/api/productos/<int:id_producto>', methods=['GET'])
def api_obtener_producto_por_id(id_producto):
    try:
        res = requests.get(f"{API_URL}/admin/productos")
        if res.status_code == 200:
            prod_data = res.json()
            productos = prod_data.get("data", prod_data) if isinstance(prod_data, dict) else prod_data

            producto = next((p for p in productos if p.get("id_producto") == id_producto or p.get("id") == id_producto), None)

            if producto:
                return jsonify({
                    "status": "success",
                    "data": producto
                }), 200
            else:
                return jsonify({
                    "status": "error",
                    "message": "Producto no encontrado"
                }), 404
        return jsonify({"status": "error", "message": "Error al consultar la API"}), res.status_code
    except requests.exceptions.RequestException:
        return jsonify({"status": "error", "message": "Error de conexión con el backend de datos"}), 500


@app.route('/api/productos', methods=['POST'])
def api_crear_producto():
    datos = request.get_json()

    if not datos or "nombre" not in datos or "precio_venta" not in datos:
        return jsonify({
            "status": "error",
            "message": "Faltan campos obligatorios (nombre, precio_venta)"
        }), 400

    try:
        res = requests.post(f"{API_URL}/admin/productos", json=datos)
        if res.status_code in [200, 201]:
            return jsonify({
                "status": "success",
                "message": "Producto creado correctamente",
                "data": res.json() if res.content else datos
            }), 201
        else:
            return jsonify({"status": "error", "message": "Error al guardar el producto en el backend"}), res.status_code
    except requests.exceptions.RequestException:
        return jsonify({"status": "error", "message": "Error de conexión con el backend de datos"}), 500


@app.route('/api/productos/<int:id_producto>', methods=['DELETE'])
def api_eliminar_producto(id_producto):
    try:
        res = requests.delete(f"{API_URL}/admin/productos/{id_producto}")
        if res.status_code in [200, 204]:
            return jsonify({
                "status": "success",
                "message": f"Producto con ID {id_producto} eliminado exitosamente"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "El producto a eliminar no fue encontrado o no se pudo procesar"
            }), 404
    except requests.exceptions.RequestException:
        return jsonify({"status": "error", "message": "Error de conexión con el backend de datos"}), 500


# --- REPORTE EXCEL ---

@app.route("/administrador/reporte/excel", methods=["GET"])
def descargar_reporte_excel():
    if "usuario" not in session:
        return redirect(url_for("login"))

    try:
        res = requests.get(f"{API_URL}/admin/productos")
        if res.status_code == 200:
            prod_data = res.json()
            productos = prod_data.get("data", prod_data) if isinstance(prod_data, dict) else prod_data
        else:
            productos = []

        df = pd.DataFrame(productos)

        if not df.empty:
            columnas_renombrar = {
                "id_producto": "ID Producto",
                "codigo_barras": "Código de Barras",
                "nombre": "Nombre del Producto",
                "precio_compra": "Precio Compra ($)",
                "precio_venta": "Precio Venta ($)",
                "stock_actual": "Stock Actual",
                "stock_minimo": "Stock Mínimo"
            }
            cols_existentes = {k: v for k, v in columnas_renombrar.items() if k in df.columns}
            df = df.rename(columns=cols_existentes)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inventario')
        output.seek(0)

        return send_file(
            output,
            download_name="Reporte_Inventario_POS.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        flash(f"Error al generar el reporte: {str(e)}", "error")
        return redirect(url_for("administrador"))


@app.route('/historial_ventas')
def historial_ventas_route():
    if "usuario" not in session:
        return redirect(url_for("login"))

    historial = []
    try:
        response = requests.get(f"{API_URL}/ventas/historial")
        
        if response.status_code == 200:
            data = response.json()
            
            # Depuración: Revisa la terminal de Flask para ver la estructura real
            print(">>> RESPUESTA DE API EN HISTORIAL:", data)
            
            # Normalización del formato JSON recibido
            if isinstance(data, list):
                historial = data
            elif isinstance(data, dict):
                historial = data.get("data") or data.get("historial") or data.get("ventas") or []
        else:
            print(f"Error de la API: Código {response.status_code}")

    except Exception as e:
        print(f"Error al conectar con el backend: {e}")

    return render_template("historial_ventas.html", historial=historial)

    


if __name__ == '__main__':
    app.run(debug=True, port=5000)