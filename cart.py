from flask import Blueprint, request, jsonify
import pymysql
from config import Config
import jwt
from functools import wraps
import logging

cart_bp = Blueprint('cart', __name__)
logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        return pymysql.connect(
            host=Config.DB_HOST,
            user=Config.DB_USERNAME,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        logger.error(f"DB Connection Failed: {e}")
        return None


# EXACT SAME AS perfumes.py — REJECTS Bearer, ACCEPTS RAW TOKEN
def verify_customer_token(request):
    token = request.headers.get('Authorization')
    if not token:
        return None, jsonify({'error': 'Token missing'}), 401
    if token.lower().startswith('bearer '):
        return None, jsonify({'error': 'Use raw token, not Bearer'}), 401
    try:
        data = jwt.decode(token.strip(), Config.SECRET_KEY, algorithms=['HS256'])
        if data.get('role_id') != 2:
            return None, jsonify({'error': 'Access denied — Customer only'}), 403
        return data, None, None
    except jwt.ExpiredSignatureError:
        return None, jsonify({'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return None, jsonify({'error': 'Invalid token'}), 401


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload, err, code = verify_customer_token(request)
        if err:
            return err, code
        request.user_id = payload['user_id']
        request.username = payload.get('username')
        return f(*args, **kwargs)
    return decorated


def verify_admin_token(request):
    token = request.headers.get('Authorization')
    if not token:
        return None, jsonify({'error': 'Token missing'}), 401
    if token.lower().startswith('bearer '):
        return None, jsonify({'error': 'Use raw token, not Bearer'}), 401
    try:
        data = jwt.decode(token.strip(), Config.SECRET_KEY, algorithms=['HS256'])
        if data.get('role_id') != 1:
            return None, jsonify({'error': 'Access denied — Admin only'}), 403
        return data, None, None
    except jwt.ExpiredSignatureError:
        return None, jsonify({'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return None, jsonify({'error': 'Invalid token'}), 401


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload, err, code = verify_admin_token(request)
        if err:
            return err, code
        request.user_id = payload['user_id']
        request.username = payload.get('username')
        return f(*args, **kwargs)
    return decorated


@cart_bp.route('/cart', methods=['POST'])
@jwt_required
def add_to_cart():
    user_id = request.user_id
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    if not items:
        return jsonify({"error": "No items provided"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Server error"}), 500

    cursor = conn.cursor()
    added = []
    errors = []

    try:
        for item in items:
            try:
                pid = int(item['perfume_id'])
                qty = int(item.get('quantity', 1))
                size = item.get('size')
            except (ValueError, TypeError):
                errors.append({"perfume_id": item.get('perfume_id'), "error": "Invalid data"})
                continue

            cursor.execute("SELECT quantity, size FROM perfumes WHERE id = %s AND available = 1", (pid,))
            perfume = cursor.fetchone()
            if not perfume:
                errors.append({"perfume_id": pid, "error": "Perfume not available"})
                continue

            stock = perfume['quantity']
            db_size = perfume['size']
            use_size = size if size else db_size

            cursor.execute(
                "SELECT quantity FROM carts WHERE user_id = %s AND perfume_id = %s AND COALESCE(size, '') = COALESCE(%s, '')",
                (user_id, pid, use_size)
            )
            current = cursor.fetchone()
            current_qty = current['quantity'] if current else 0
            new_total = current_qty + qty
            if new_total > stock:
                errors.append({"perfume_id": pid, "error": f"Only {stock} in stock (you have {current_qty})"})
                continue

            cursor.execute("""
                INSERT INTO carts (user_id, perfume_id, quantity, size)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity),
                    size = COALESCE(VALUES(size), size)
            """, (user_id, pid, new_total, use_size))

            added.append({"perfume_id": pid, "total_in_cart": new_total, "size": use_size})

        conn.commit()

        if errors and not added:
            return jsonify({"errors": errors}), 400
        if errors:
            return jsonify({"message": "Partial success", "added": added, "errors": errors}), 207

        return jsonify({"message": "All added", "added": added}), 201

    except Exception as e:
        conn.rollback()
        logger.error(f"Add to cart error (user {user_id}): {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()


@cart_bp.route('/cart', methods=['GET'])
@jwt_required
def view_cart():
    user_id = request.user_id
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Server error"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.perfume_id, p.name, p.price, c.quantity, COALESCE(c.size, p.size) AS size,
                   p.quantity AS stock, c.added_at
            FROM carts c
            JOIN perfumes p ON c.perfume_id = p.id
            WHERE c.user_id = %s
            ORDER BY c.added_at DESC
        """, (user_id,))
        items = cursor.fetchall()
        base_url = request.host_url.rstrip('/')

        for item in items:
            item['photo_url'] = f"{base_url}/perfumes/photo/{item['perfume_id']}"
            item['in_stock'] = item['stock'] >= item['quantity']

        return jsonify({"cart_items": items}), 200

    except Exception as e:
        logger.error(f"View cart error (user {user_id}): {e}")
        return jsonify({"error": "Failed to load cart"}), 500
    finally:
        conn.close()


@cart_bp.route('/cart/<int:perfume_id>', methods=['DELETE'])
@jwt_required
def remove_from_cart(perfume_id):
    user_id = request.user_id
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Server error"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM carts WHERE user_id = %s AND perfume_id = %s", (user_id, perfume_id))
        if cursor.rowcount == 0:
            return jsonify({"error": "Item not in your cart"}), 404

        conn.commit()
        return jsonify({"message": "Item removed"}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"Delete error (user {user_id}): {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()


# ==================== ADD TO YOUR EXISTING FILE (bottom) ====================
# Backwards-compatible: accept POST /orders (legacy) as well as /checkout
@cart_bp.route('/orders', methods=['POST'])
@cart_bp.route('/checkout', methods=['POST'])
@jwt_required
def checkout():
    user_id = request.user_id
    data = request.get_json(silent=True) or {}

    # === STRICT VALIDATION ===
    required = ['shipping', 'payment_method', 'items', 'totalPrice', 'tax', 'shippingCost']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    shipping = data['shipping']
    payment_method = data['payment_method'].lower()
    items = data['items']
    card_details = data.get('card_details', {})

    if payment_method not in ['card', 'cod']:
        return jsonify({"error": "payment_method must be 'card' or 'cod'"}), 400

    if not items or not isinstance(items, list):
        return jsonify({"error": "Items must be a non-empty list"}), 400

    # Validate shipping
    ship_keys = ['firstName', 'lastName', 'email', 'phone', 'address', 'city', 'state', 'zip']
    for key in ship_keys:
        if not shipping.get(key) or not str(shipping[key]).strip():
            return jsonify({"error": f"Shipping {key} is required and cannot be empty"}), 400

    # Validate card if needed
    if payment_method == 'card':
        card_keys = ['cardName', 'cardNumber', 'expiry', 'cvv']
        for key in card_keys:
            value = card_details.get(key)
            if not value or not str(value).strip():
                return jsonify({"error": f"Card {key} is required"}), 400
            if key == 'cardNumber' and (len(value.replace(' ', '')) < 13 or len(value.replace(' ', '')) > 19):
                return jsonify({"error": "Invalid card number"}), 400
            if key == 'cvv' and not (value.isdigit() and len(value) in [3, 4]):
                return jsonify({"error": "CVV must be 3 or 4 digits"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    cursor = conn.cursor()

    try:
        # === 1. Create Order ===
        cursor.execute("""
            INSERT INTO orders (
                user_id, total_amount, shipping_cost, tax_amount,
                shipping_first_name, shipping_last_name, shipping_email,
                shipping_phone, shipping_address, shipping_city,
                shipping_state, shipping_zip, payment_method, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            float(data['totalPrice']),
            float(data['shippingCost']),
            float(data['tax']),
            shipping['firstName'].strip(),
            shipping['lastName'].strip(),
            shipping['email'].strip().lower(),
            shipping['phone'].strip(),
            shipping['address'].strip(),
            shipping['city'].strip(),
            shipping['state'].strip(),
            shipping['zip'].strip(),
            payment_method,
            'pending'
        ))
        order_id = cursor.lastrowid

        # === 2. Process Items & Deduct Stock ===
        for item in items:
            try:
                perfume_id = int(item['perfume_id'])
                quantity = int(item['quantity'])
                size = item.get('selectedSize') or None
                unit_price = float(item['price'])
            except (KeyError, ValueError, TypeError):
                conn.rollback()
                return jsonify({"error": "Invalid item data format"}), 400

            if quantity <= 0:
                return jsonify({"error": "Quantity must be positive"}), 400

            # Check availability
            cursor.execute("SELECT quantity, name FROM perfumes WHERE id = %s AND available = 1", (perfume_id,))
            perfume = cursor.fetchone()
            if not perfume:
                conn.rollback()
                return jsonify({"error": f"Perfume ID {perfume_id} not found or unavailable"}), 404

            if perfume['quantity'] < quantity:
                conn.rollback()
                return jsonify({
                    "error": f"Only {perfume['quantity']} left of {perfume['name']}"
                }), 400

            # Add to order
            cursor.execute("""
                INSERT INTO order_items (order_id, perfume_id, quantity, size, unit_price)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, perfume_id, quantity, size, unit_price))

            # Deduct stock
            cursor.execute("UPDATE perfumes SET quantity = quantity - %s WHERE id = %s", (quantity, perfume_id))

        # === 3. Save Card (masked) ===
        if payment_method == 'card':
            last4 = str(card_details['cardNumber']).replace(' ', '')[-4:]
            cursor.execute("""
                INSERT INTO payment_details 
                (order_id, payment_method, card_last4, card_holder_name, expiry)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, 'card', last4, card_details['cardName'], card_details['expiry']))

        # === 4. Clear Cart ===
        cursor.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))

        # === 5. Final Status ===
        final_status = 'paid' if payment_method == 'card' else 'cod_pending'
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (final_status, order_id))

        conn.commit()

        return jsonify({
            "message": "Order placed successfully!",
            "order_id": order_id,
            "status": final_status,
            "payment_method": payment_method,
            "total": float(data['totalPrice']) + float(data['shippingCost']) + float(data['tax'])
        }), 201

    except Exception as e:
        conn.rollback()
        logger.error(f"Checkout failed (user {user_id}): {str(e)}")
        return jsonify({"error": "Order failed. Please try again later."}), 500
    finally:
        cursor.close()
        conn.close()


# === GET USER ORDERS (with items) ===
@cart_bp.route('/orders', methods=['GET'])
@jwt_required
def get_orders():
    user_id = request.user_id
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Server error"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id, total_amount, status, payment_method, created_at,
                shipping_first_name, shipping_last_name, shipping_city,
                shipping_address, shipping_zip
            FROM orders 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        orders = cursor.fetchall()

        for order in orders:
            cursor.execute("""
                SELECT 
                    oi.perfume_id, p.name, oi.quantity, oi.size, 
                    oi.unit_price, (oi.quantity * oi.unit_price) as subtotal
                FROM order_items oi
                JOIN perfumes p ON oi.perfume_id = p.id
                WHERE oi.order_id = %s
            """, (order['id'],))
            order['items'] = cursor.fetchall()

        return jsonify({"orders": orders}), 200

    except Exception as e:
        logger.error(f"Get orders failed (user {user_id}): {e}")
        return jsonify({"error": "Failed to load orders"}), 500
    finally:
        conn.close()



# === RECENT ORDERS – India-Optimized (Hyderabad Time, ₹, Clean UI) ===
# === RECENT ORDERS – ONLY USER'S OWN (Ultra Simple & Safe) ===
@cart_bp.route('/recent-orders', methods=['GET'])
@jwt_required
def recent_orders():
    user_id = request.user_id  # Guaranteed to be the logged-in user only
    limit = request.args.get('limit', 5, type=int)
    if limit < 1: limit = 1
    if limit > 20: limit = 20

    conn = get_db_connection()
    if not conn:
        return jsonify({"recent_orders": [], "count": 0, "message": "Loading..."}), 200

    try:
        cursor = conn.cursor()

        # 1. Get only this user's recent orders
        cursor.execute("""
            SELECT id, total_amount, shipping_cost, tax_amount, status, 
                   payment_method, created_at, shipping_city
            FROM orders 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (user_id, limit))

        orders = cursor.fetchall()
        if not orders:
            return jsonify({"recent_orders": [], "count": 0, "message": "No orders yet"}), 200

        result = []
        base_url = request.host_url.rstrip('/')

        for order in orders:
            order_id = order['id']
            
            # 2. Get items for this specific order only
            cursor.execute("""
                SELECT p.name, oi.quantity, oi.unit_price, oi.perfume_id
                FROM order_items oi
                JOIN perfumes p ON oi.perfume_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            items = cursor.fetchall()

            # Build clean response
            order_data = {
                "order_id": order_id,
                "date": order['created_at'].strftime("%d %b %Y"),
                "time": order['created_at'].strftime("%I:%M %p"),
                "city": order['shipping_city'],
                "status": order['status'],
                "grand_total": round(float(order['total_amount']) + 
                                   float(order.get('shipping_cost') or 0) + 
                                   float(order['tax_amount']), 2),
                "items": [
                    {
                        "name": item['name'],
                        "quantity": item['quantity'],
                        "photo": f"{base_url}/perfumes/photo/{item['perfume_id']}"
                    } for item in items
                ],
                "items_count": len(items)
            }
            result.append(order_data)

        return jsonify({
            "recent_orders": result,
            "count": len(result),
            "message": "Your latest orders"
        }), 200

    except Exception as e:
        logger.error(f"User {user_id} recent orders: {e}")
        return jsonify({"recent_orders": [], "count": 0, "message": "Try again"}), 200
    finally:
        cursor.close()
        conn.close()



# ======================================================================
# ADMIN PANEL: View & Manage All Orders + Payments
# ======================================================================

@cart_bp.route('/admin/orders', methods=['GET'])
@admin_required
def admin_list_orders():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB unavailable"}), 500

    try:
        cursor = conn.cursor()
        page = max(1, request.args.get('page', 1, type=int))
        per_page = min(50, request.args.get('per_page', 20, type=int))
        status = request.args.get('status')
        user_id = request.args.get('user_id', type=int)
        offset = (page - 1) * per_page

        sql = """
            SELECT id, user_id, (SELECT username FROM users WHERE id = orders.user_id), total_amount, shipping_cost, tax_amount,
                   status, payment_method, created_at
            FROM orders WHERE 1=1
        """
        params = []
        if status:
            sql += " AND status = %s"
            params.append(status)
        if user_id:
            sql += " AND user_id = %s"
            params.append(user_id)
        sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(sql, params)
        orders = cursor.fetchall()

        count_sql = "SELECT COUNT(*) AS total FROM orders WHERE 1=1"
        count_params = []
        if status:
            count_sql += " AND status = %s"
            count_params.append(status)
        if user_id:
            count_sql += " AND user_id = %s"
            count_params.append(user_id)
        cursor.execute(count_sql, count_params)
        total = cursor.fetchone()['total']

        return jsonify({
            "orders": orders,
            "pagination": {
                "page": page, "per_page": per_page, "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }), 200
    except Exception as e:
        logger.error(f"Admin list orders error: {e}")
        return jsonify({"error": "Failed to fetch orders"}), 500
    finally:
        conn.close()


@cart_bp.route('/admin/orders/<int:order_id>', methods=['GET'])
@admin_required
def admin_get_order(order_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB unavailable"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT *, (SELECT username FROM users WHERE id = orders.user_id) FROM orders WHERE id = %s", (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({"error": "Order not found"}), 404

        cursor.execute("""
            SELECT oi.perfume_id, p.name, oi.quantity, oi.size,
                   oi.unit_price, (oi.quantity * oi.unit_price) AS subtotal
            FROM order_items oi
            JOIN perfumes p ON oi.perfume_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        order['items'] = cursor.fetchall()

        cursor.execute("SELECT payment_method, card_last4, card_holder_name, expiry FROM payment_details WHERE order_id = %s", (order_id,))
        order['payment'] = cursor.fetchone()

        return jsonify({"order": order}), 200
    except Exception as e:
        logger.error(f"Admin get order {order_id} error: {e}")
        return jsonify({"error": "Failed to load order"}), 500
    finally:
        conn.close()


@cart_bp.route('/admin/orders/<int:order_id>/status', methods=['PATCH'])
@admin_required
def admin_update_order_status(order_id):
    # Debug: log request summary (avoid logging sensitive Authorization header value)
    try:
        auth_present = 'Authorization' in request.headers
    except Exception:
        auth_present = False
    logger.debug(f"admin_update_order_status called: method={request.method} path={request.path} args={request.args.to_dict()} form_keys={list(request.form.keys())} json_present={bool(request.get_json(silent=True))} auth_present={auth_present}")

    # Accept status from JSON body, form-encoded body, or ?status= query param
    data = request.get_json(silent=True) or {}
    if not data:
        # fallback to form data
        data = request.form or {}
    new_status = data.get('status') or request.args.get('status')

    allowed = {'pending', 'paid', 'cod_pending', 'shipped', 'delivered', 'cancelled'}

    if new_status is None:
        return jsonify({"error": "Missing 'status' (provide JSON body {\"status\": ...}, form data, or ?status=...)"}), 400

    # normalize
    try:
        new_status = str(new_status).strip().lower()
    except Exception:
        return jsonify({"error": "Invalid status format"}), 400

    if new_status not in allowed:
        return jsonify({"error": f"Invalid status '{new_status}'. Allowed: {', '.join(sorted(allowed))}"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB unavailable"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE id = %s FOR UPDATE", (order_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Order not found"}), 404

        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
        conn.commit()
        return jsonify({"message": "Status updated", "new_status": new_status}), 200
    except Exception as e:
        conn.rollback()
        logger.error(f"Admin update status {order_id}: {e}")
        return jsonify({"error": "Update failed"}), 500
    finally:
        conn.close()


@cart_bp.route('/admin/payments', methods=['GET'])
@admin_required
def admin_list_payments():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB unavailable"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pd.id, pd.order_id, o.user_id, pd.payment_method,
                   pd.card_last4, pd.card_holder_name, pd.expiry, pd.created_at
            FROM payment_details pd
            JOIN orders o ON pd.order_id = o.id
            ORDER BY pd.created_at DESC
        """)
        payments = cursor.fetchall()
        return jsonify({"payments": payments}), 200
    except Exception as e:
        logger.error(f"Admin list payments error: {e}")
        return jsonify({"error": "Failed to load payments"}), 500
    finally:
        conn.close()