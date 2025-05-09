import boto3
from config import AWS_REGION, DYNAMODB_USERS_TABLE, DYNAMODB_INVENTORY_TABLE, DYNAMODB_SHIPMENTS_TABLE

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

users_table = dynamodb.Table(DYNAMODB_USERS_TABLE)
inventory_table = dynamodb.Table(DYNAMODB_INVENTORY_TABLE)
shipments_table = dynamodb.Table(DYNAMODB_SHIPMENTS_TABLE)

def get_all_shipments():
    response = shipments_table.scan()
    return response.get('Items', [])

def get_all_users():
    response = users_table.scan()
    return response.get('Items', [])

def get_inventory():
    return inventory_table.scan().get('Items', [])

def add_inventory(product_id, name, qty, store_id, supplier_id, threshold):
    inventory_table.put_item(Item={
        'ProductID': product_id,
        'ProductName': name,
        'Quantity': qty,
        'StoreID': store_id,
        'SupplierID': supplier_id,
        'ThresholdQty': threshold
    })

def update_quantity(product_id, qty):
    inventory_table.update_item(
        Key={'ProductID': product_id},
        UpdateExpression='SET Quantity = :val',
        ExpressionAttributeValues={':val': qty}
    )

def add_shipment(shipment_id, product_id, quantity, supplier_id, store_id,status):
    shipments_table.put_item(Item={
        'ShipmentID': shipment_id,
        'ProductID': product_id,
        'Quantity': quantity,
        'SupplierID': supplier_id,
        'StoreID': store_id,
        'Status': status
    })

def update_shipment_status(shipment_id, new_status):
    shipments_table.update_item(
        Key={'ShipmentID': shipment_id},
        UpdateExpression='SET #s = :val',
        ExpressionAttributeNames={'#s': 'Status'},
        ExpressionAttributeValues={':val': new_status}
    )
