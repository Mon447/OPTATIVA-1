from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import json
from database import get_db_connection

app = FastAPI(title="POS API REST")

# --- SCHEMAS DE PYDANTIC ---

class LoginSchema(BaseModel):
    username: str
    password: str

class MovimientoSchema(BaseModel):
    id_producto: int
    tipo_movimiento: str
    cantidad: int
    id_usuario: Optional[int] = 1
    motivo: Optional[str] = ""

class ItemVenta(BaseModel):
    id_producto: int
    cantidad: int
    precio_unitario: Optional[float] = None

class VentaSchema(BaseModel):
    id_usuario: Optional[int] = 1
    cliente: Optional[str] = "Cliente General"
    nombre_cliente: Optional[str] = "Cliente General"
    productos: Optional[List[ItemVenta]] = []
    items: Optional[List] = []

class DevolucionSchema(BaseModel):
    id_venta: int
    id_producto: int
    cantidad: int
    motivo: str

class ProductoSchema(BaseModel):
    codigo_barras: str
    nombre: str
    precio_compra: float
    precio_venta: float
    stock_actual: int
    stock_minimo: int
    id_proveedor: Optional[int] = None

# --- ENDPOINTS ---

@app.post("/api/auth/login")
def login(data: LoginSchema):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM fn_autenticar_usuario(%s, %s)", (data.username, data.password))
        user = cur.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        return {"success": True, "usuario": user}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/api/almacen/movimiento")
def movimiento_almacen(data: MovimientoSchema):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO movimientos_inventario (id_producto, tipo_movimiento, cantidad, id_usuario, motivo) VALUES (%s, %s, %s, %s, %s)",
            (data.id_producto, data.tipo_movimiento, data.cantidad, data.id_usuario, data.motivo)
        )
        conn.commit()
        return {"success": True, "message": "Movimiento registrado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/api/ventas")
@app.post("/api/ventas/realizar")
def registrar_venta(data: VentaSchema):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cliente_final = data.cliente or data.nombre_cliente or "Cliente General"
        items_lista = data.productos if data.productos else data.items
        
        if not items_lista:
            raise HTTPException(status_code=400, detail="La lista de productos no puede estar vacía")

        items_json = []
        for item in items_lista:
            # Desempaquetado seguro de diccionarios o modelos de Pydantic
            if hasattr(item, "dict"):
                item_dict = item.dict()
            elif isinstance(item, dict):
                item_dict = item
            else:
                item_dict = dict(item)

            prod_id = item_dict.get("id_producto")
            cant = item_dict.get("cantidad", 1)
            
            # Consultar precio_venta si no viene provisto
            precio = item_dict.get("precio_unitario") or item_dict.get("precio") or item_dict.get("precio_venta")
            
            if precio is None:
                cur.execute("SELECT precio_venta FROM productos WHERE id_producto = %s", (prod_id,))
                res_prod = cur.fetchone()
                if res_prod:
                    precio = float(res_prod[0] if isinstance(res_prod, (tuple, list)) else res_prod.get("precio_venta", 0))
                else:
                    precio = 0.0

            items_json.append({
                "id_producto": int(prod_id),
                "cantidad": int(cant),
                "precio": float(precio),
                "precio_venta": float(precio),
                "precio_unitario": float(precio)
            })

        print(">>> REGISTRANDO VENTA PARA CLIENTE:", cliente_final)
        print(">>> PRODUCTOS A PROCESAR:", json.dumps(items_json))

        # Ejecución del procedimiento almacenado
        cur.execute(
            "CALL sp_registrar_venta(%s, %s, %s, NULL)",
            (data.id_usuario or 1, cliente_final, json.dumps(items_json))
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {"success": True, "message": "Venta procesada con éxito"}

    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        print("!!! ERROR EN REGISTRAR VENTA:", str(e))
        raise HTTPException(status_code=500, detail=f"Error al procesar la venta: {str(e)}")

@app.post("/api/ventas/devolucion")
def registrar_devolucion(data: DevolucionSchema):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO devoluciones (id_venta, id_producto, cantidad, motivo) VALUES (%s, %s, %s, %s)",
            (data.id_venta, data.id_producto, data.cantidad, data.motivo)
        )
        conn.commit()
        return {"success": True, "message": "Devolución completada"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/api/admin/productos")  
def obtener_productos():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT 
                p.id_producto,
                p.codigo_barras,
                p.nombre,
                p.precio_compra,
                p.precio_venta,
                p.stock_actual,
                p.stock_minimo,
                p.id_proveedor,
                pr.nombre_empresa AS nombre_proveedor
            FROM productos p
            LEFT JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor;
        """
        cursor.execute(query)
        productos = cursor.fetchall()
        return productos
    finally:
        cursor.close()
        conn.close()

@app.post("/api/admin/productos")
def crear_producto(p: ProductoSchema):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO productos 
                (codigo_barras, nombre, precio_compra, precio_venta, stock_actual, stock_minimo, id_proveedor) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (p.codigo_barras, p.nombre, p.precio_compra, p.precio_venta, p.stock_actual, p.stock_minimo, p.id_proveedor)
        )
        nuevo = cur.fetchone()
        conn.commit()
        return nuevo
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.delete("/api/admin/productos/{id_producto}")
def eliminar_producto(id_producto: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM productos WHERE id_producto = %s", (id_producto,))
        conn.commit()
        return {"success": True, "message": "Producto eliminado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/api/admin/proveedores")
def get_proveedores():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id_proveedor, nombre_empresa FROM proveedores;")
        proveedores = cursor.fetchall()
        return proveedores
    finally:
        cursor.close()
        conn.close()

@app.get("/api/ventas/historial")
def obtener_historial_ventas():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT 
                v.id_venta,
                v.fecha_venta,
                p.nombre AS producto,
                dv.cantidad AS cantidad_vendida,
                dv.precio_unitario,
                dv.subtotal,
                p.stock_actual AS stock_restante
            FROM detalle_venta dv
            JOIN ventas v ON dv.id_venta = v.id_venta
            JOIN productos p ON dv.id_producto = p.id_producto
            ORDER BY v.fecha_venta DESC;
        """
        cursor.execute(query)
        filas = cursor.fetchall()
        
        historial = []
        for row in filas:
            if isinstance(row, dict):
                id_venta = row["id_venta"]
                fecha_venta = row["fecha_venta"]
                producto = row["producto"]
                cantidad = row["cantidad_vendida"]
                precio = row["precio_unitario"]
                subtotal = row["subtotal"]
                stock = row["stock_restante"]
            else:
                id_venta, fecha_venta, producto, cantidad, precio, subtotal, stock = row

            historial.append({
                "id_venta": id_venta,
                "fecha_venta": str(fecha_venta) if fecha_venta else "",
                "producto": producto,
                "cantidad_vendida": cantidad,
                "precio_unitario": float(precio) if precio is not None else 0.0,
                "subtotal": float(subtotal) if subtotal is not None else 0.0,
                "stock_restante": stock
            })
            
        return historial

    except Exception as e:
        print("ERROR EN HISTORIAL:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()