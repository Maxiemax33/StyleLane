from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, send_file
import json
import csv
from io import StringIO
from dynamodb_handler import add_inventory, update_quantity, get_inventory, get_all_shipments, get_all_users, add_shipment
from sns_handler import send_sns

app = Flask(__name__)

# --- Fake session simulation ---
fake_session = {}

# --- Role-based access control ---
def role_required(allowed_roles):
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_cookie = request.cookies.get("user")
            if user_cookie:
                user_data = json.loads(user_cookie)
                if user_data.get("role") in allowed_roles:
                    return func(*args, **kwargs)
            return "Access denied", 403
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

# --- Routes ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]

    if username == "admin" and password == "admin" and role == "Admin":
        resp = make_response(redirect("/admin"))
        resp.set_cookie("user", json.dumps({"username": username, "role": "Admin"}))
        return resp
    elif username == "manager" and password == "manager" and role == "Inventory Manager":
        resp = make_response(redirect("/inventory"))
        resp.set_cookie("user", json.dumps({"username": username, "role": "Inventory Manager"}))
        return resp
    elif username == "supplier" and password == "supplier" and role == "Supplier":
        resp = make_response(redirect("/supplier"))
        resp.set_cookie("user", json.dumps({"username": username, "role": "Supplier"}))
        return resp
    else:
        return render_template("login.html", error="Invalid credentials")

@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.delete_cookie("user")
    return resp

@app.route("/admin")
@role_required(["Admin"])
def admin_dashboard():
    users = get_all_users()
    inventory = get_inventory()
    shipments = get_all_shipments()
    return render_template("admin_dashboard.html", users=users, inventory=inventory, shipments=shipments,
                           total_users=len(users), total_inventory=len(inventory), total_shipments=len(shipments))

@app.route("/inventory")
@role_required(["Inventory Manager"])
def inventory_page():
    inventory = get_inventory()
    shipments = get_all_shipments()
    return render_template("inventory.html", inventory=inventory, shipments=shipments)

@app.route("/inventory-data")
def get_inventory_route():
    return jsonify(get_inventory())

@app.route("/add-inventory", methods=["POST"])
def add_inv():
    data = request.json
    add_inventory(
        product_id=data['ProductID'],
        name=data['ProductName'],
        qty=data['Quantity'],
        store_id=data['StoreID'],
        supplier_id=data['SupplierID'],
        threshold=data['ThresholdQty']
    )
    return jsonify({"message": "Product added!"})

@app.route("/update-qty", methods=["POST"])
def update_qty():
    ProductID = request.form["ProductID"]
    Quantity = int(request.form["Quantity"])
    ThresholdQty = int(request.form["ThresholdQty"])
    from dynamodb_handler import inventory_table
    response = inventory_table.get_item(Key={'ProductID': ProductID})
    item = response.get('Item')
    if not item:
        return "Product not found", 404

    item['Quantity'] = Quantity
    item['ThresholdQty'] = ThresholdQty
    inventory_table.put_item(Item=item)

    if Quantity < ThresholdQty:
        alert_message = f"⚠️ {ProductID} is low in stock!\nCurrent Qty: {Quantity}"
        send_sns("low_stock", alert_message, subject="Low Stock Alert - StyleLane")

    return redirect("/inventory?success=1")

@app.route("/add-shipment", methods=["POST"])
def add_shipment_route():
    data = request.form
    add_shipment(data["ShipmentID"], data["ProductID"], int(data["Quantity"]), data["SupplierID"], data["StoreID"], data["Status"])
    message = f"Shipment {data['ShipmentID']} confirmed: {data['Quantity']} units of {data['ProductID']} dispatched by {data['SupplierID']} to Store {data['StoreID']}."
    send_sns("shipment", message, subject="Shipment Confirmation")
    return redirect("/supplier?success=1")

@app.route("/restock-request", methods=["POST"])
def restock_request():
    data = request.json
    message = f"Restock Request: {data['ProductID']} for Store {data['StoreID']} by Manager {data['ManagerName']}.\nRequested Qty: {data['Quantity']}"
    send_sns("restock", message, subject="Restock Request")
    return jsonify({"message": "Restock request sent to supplier!"})

@app.route("/supplier")
@role_required(["Supplier"])
def supplier_dashboard():
    shipments = get_all_shipments()
    success = request.args.get("success") == "1"
    return render_template("supplier.html", shipments=shipments, success=success)

@app.route("/shipments")
def get_shipments():
    try:
        return jsonify(get_all_shipments())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/view-users")
def view_users():
    role = request.args.get("role")
    if role.lower() != "admin":
        return "Access denied", 403
    return jsonify({"users": ["admin", "manager", "supplier"]})

@app.route("/users")
def get_users():
    try:
        return jsonify(get_all_users())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/export-full-report")
def export_full_report():
    try:
        users = get_all_users()
        inventory = get_inventory()
        shipments = get_all_shipments()

        filename = "StyleLane_Report.csv"
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Users"])
            writer.writerow(["Username", "Role"])
            for user in users:
                writer.writerow([user.get('Username', ''), user.get('Role', '')])
            writer.writerow([])

            writer.writerow(["Inventory"])
            writer.writerow(["ProductID", "ProductName", "Quantity", "StoreID", "SupplierID", "ThresholdQty"])
            for item in inventory:
                writer.writerow([
                    item.get('ProductID', ''), item.get('ProductName', ''),
                    item.get('Quantity', ''), item.get('StoreID', ''),
                    item.get('SupplierID', ''), item.get('ThresholdQty', '')
                ])
            writer.writerow([])

            writer.writerow(["Shipments"])
            writer.writerow(["ShipmentID", "ProductID", "Quantity", "SupplierID", "StoreID", "Status"])
            for s in shipments:
                writer.writerow([
                    s.get('ShipmentID', ''), s.get('ProductID', ''),
                    s.get('Quantity', ''), s.get('SupplierID', ''),
                    s.get('StoreID', ''), s.get('Status', '')
                ])
        return send_file(filename, mimetype='text/csv', as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/mark-received", methods=["POST"])
def mark_shipment_received():
    shipment_id = request.form["shipment_id"]
    from dynamodb_handler import update_shipment_status
    update_shipment_status(shipment_id, "Received")
    return redirect("/inventory?received=1")

if __name__ == "__main__":
    app.run(debug=True)
