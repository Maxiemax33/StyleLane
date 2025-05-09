import os

AWS_REGION = "eu-north-1"  # or your region
DYNAMODB_USERS_TABLE = "StyleLane_Users"
DYNAMODB_INVENTORY_TABLE = "StyleLane_Inventory"
DYNAMODB_SHIPMENTS_TABLE = "StyleLane_Shipments"

SNS_TOPICS = {
    "low_stock": "arn:aws:sns:eu-north-1:072244248629:LowStockAlerts",
    "restock": "arn:aws:sns:eu-north-1:072244248629:RestockRequests",
    "shipment": "arn:aws:sns:eu-north-1:072244248629:ShipmentConfirmations"
}
