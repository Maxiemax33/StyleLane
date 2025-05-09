from fastapi import FastAPI, Request, Form, Cookie,Depends, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import List
import pandas as pd
import json
import csv
from io import StringIO
from fastapi.staticfiles import StaticFiles
from typing import Optional
from starlette.status import HTTP_303_SEE_OTHER
from dynamodb_handler import add_inventory, update_quantity, get_inventory, get_all_shipments, get_all_users, add_shipment, get_all_shipments
from sns_handler import send_sns

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Session simulation ---
fake_session = {}

# --- Role-based dependency ---

def role_required(allowed_roles: List[str]):
    def wrapper(request: Request):
        user = request.cookies.get("user")
        if user:
            import json
            user_data = json.loads(user)
            if user_data.get("role") in allowed_roles:
                return True
        raise HTTPException(status_code=403, detail="Access denied")
    return wrapper

# --- Routes ---
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    # Dummy login check (replace with your logic)
    if username == "admin" and password == "admin" and role == "Admin":
        response = RedirectResponse(url="/admin", status_code=302)
        response.set_cookie(key="user",value=json.dumps({"username": username, "role": "Admin"}),httponly=True)
        return response
    elif username == "manager" and password == "manager" and role == "Inventory Manager":
        response = RedirectResponse(url="/inventory", status_code=302)
        response.set_cookie(key="user",value=json.dumps({"username": username, "role": "Inventory Manager"}),httponly=True)
        return response
    elif username == "supplier" and password == "supplier" and role == "Supplier":
        response = RedirectResponse(url="/supplier", status_code=302)
        response.set_cookie(key="user",value=json.dumps({"username": username, "role": "Supplier"}),httponly=True)
        return response
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("role")
    return response

@app.get("/admin")
async def admin_dashboard(request: Request, role_check: None = Depends(role_required(["Admin"]))):
    users = get_all_users()
    inventory = get_inventory()
    shipments = get_all_shipments()

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "users": users,
        "inventory": inventory,
        "shipments": shipments,
        "total_users": len(users),
        "total_inventory": len(inventory),
        "total_shipments": len(shipments)
    })

@app.get("/inventory")
async def inventory_page(request: Request, role_check: bool = Depends(role_required(["Inventory Manager"]))):
    inventory = get_inventory()
    shipments = get_all_shipments()
    return templates.TemplateResponse("inventory.html", {
        "request": request,
        "inventory": inventory,
        "shipments": shipments
    })


@app.get("/inventory-data")
def get_inventory_route():
    items = get_inventory()
    return JSONResponse(content=items)


@app.post("/add-inventory")
def add_inv(data: dict):
    add_inventory(
        product_id=data['ProductID'],
        name=data['ProductName'],
        qty=data['Quantity'],
        store_id=data['StoreID'],
        supplier_id=data['SupplierID'],
        threshold=data['ThresholdQty']
    )
    return {"message": "Product added!"}

@app.post("/update-qty")
def update_qty(
    ProductID: str = Form(...),
    Quantity: int = Form(...),
    ThresholdQty: int = Form(...)
):
    # Step 1: Fetch full existing item from DynamoDB
    from dynamodb_handler import inventory_table  # Only if not already imported
    response = inventory_table.get_item(Key={'ProductID': ProductID})
    item = response.get('Item')

    if not item:
        raise HTTPException(status_code=404, detail=f"Product {ProductID} not found.")

    # Step 2: Update quantity and threshold in the full item
    item['Quantity'] = Quantity
    item['ThresholdQty'] = ThresholdQty

    # Step 3: Reinsert the updated item
    inventory_table.put_item(Item=item)

    # Step 4: Send SNS alert if quantity is below threshold
    if Quantity < ThresholdQty:
        alert_message = f"⚠️ {ProductID} is low in stock!\nCurrent Qty: {Quantity}"
        send_sns("low_stock", alert_message, subject="Low Stock Alert - StyleLane")

    return RedirectResponse(url="/inventory?success=1", status_code=HTTP_303_SEE_OTHER)

@app.post("/add-shipment")
def add_shipment_route(
    ShipmentID: str = Form(...),
    ProductID: str = Form(...),
    Quantity: int = Form(...),
    SupplierID: str = Form(...),
    StoreID: str = Form(...),
    Status: str = Form(...)
):
    # Call the original function using positional arguments
    add_shipment(ShipmentID, ProductID, Quantity, SupplierID, StoreID,Status)

    message = f"Shipment {ShipmentID} confirmed: {Quantity} units of {ProductID} dispatched by {SupplierID} to Store {StoreID}."
    send_sns("shipment", message, subject="Shipment Confirmation")
    response = RedirectResponse(url="/supplier?success=1", status_code=HTTP_303_SEE_OTHER)
    return response

@app.post("/restock-request")
def restock_request(data: dict):
    message = f"Restock Request: {data['ProductID']} for Store {data['StoreID']} by Manager {data['ManagerName']}.\nRequested Qty: {data['Quantity']}"
    send_sns("restock", message, subject="Restock Request")
    return {"message": "Restock request sent to supplier!"}

@app.get("/supplier")
async def supplier_dashboard(request: Request, role_check: None = Depends(role_required(["Supplier"]))):
    shipments = get_all_shipments()
    print("Fetched Shipments:", shipments)  # ← add this line
    return templates.TemplateResponse("supplier.html", {
        "request": request,
        "shipments": shipments,
        "success": request.query_params.get("success") == "1"
    })

@app.get("/shipments")
def get_shipments():
    try:
        shipments = get_all_shipments()
        return shipments
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/view-users")
def view_users(role: str):
    if role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    # Return mock user list or actual data
    return {"users": ["admin", "manager", "supplier"]}


@app.get("/users")
def get_users():
    try:
        users = get_all_users()
        return users
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/export-full-report")
def export_full_report():
    try:
        users = get_all_users()
        inventory = get_inventory()
        shipments = get_all_shipments()

        filename = "StyleLane_Report.csv"
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)

            # Write Users
            writer.writerow(["Users"])
            writer.writerow(["Username", "Role"])
            for user in users:
                writer.writerow([user.get('Username', ''), user.get('Role', '')])

            writer.writerow([])

            # Write Inventory
            writer.writerow(["Inventory"])
            writer.writerow(["ProductID", "ProductName", "Quantity", "StoreID", "SupplierID", "ThresholdQty"])
            for item in inventory:
                writer.writerow([
                    item.get('ProductID', ''),
                    item.get('ProductName', ''),
                    item.get('Quantity', ''),
                    item.get('StoreID', ''),
                    item.get('SupplierID', ''),
                    item.get('ThresholdQty', '')
                ])

            writer.writerow([])

            # Write Shipments
            writer.writerow(["Shipments"])
            writer.writerow(["ShipmentID", "ProductID", "Quantity", "SupplierID", "StoreID", "Status"])
            for s in shipments:
                writer.writerow([
                    s.get('ShipmentID', ''),
                    s.get('ProductID', ''),
                    s.get('Quantity', ''),
                    s.get('SupplierID', ''),
                    s.get('StoreID', ''),
                    s.get('Status', '')
                ])

        return FileResponse(filename, media_type='text/csv', filename=filename)

    except Exception as e:
        print("Error exporting full report:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/mark-received")
def mark_shipment_received(shipment_id: str = Form(...)):
    from dynamodb_handler import update_shipment_status
    update_shipment_status(shipment_id, "Received")
    return RedirectResponse(url="/inventory?received=1", status_code=HTTP_303_SEE_OTHER)
