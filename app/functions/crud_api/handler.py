"""130.crud-api - CRUD API simulating a web-store shopping cart.

Adapted from the SeBS NoSQL benchmark 130.crud-api (Copik et al., 2021; Schmid et al.,
2025) for direct deployment with AWS SAM. The table name is read from TABLE_NAME, which
is the parameter changed by fault F3.
"""
import json
import os
import time
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def add_product(cart_id, product_id, name, price, quantity):
    TABLE.put_item(
        Item={
            "cart_id": cart_id,
            "product_id": product_id,
            "name": name,
            "price": Decimal(str(price)),
            "quantity": quantity,
        }
    )


def get_product(cart_id, product_id):
    return TABLE.get_item(Key={"cart_id": cart_id, "product_id": product_id}).get("Item")


def query_cart(cart_id):
    resp = TABLE.query(
        KeyConditionExpression=Key("cart_id").eq(cart_id)
    )
    items = resp.get("Items", [])
    total = sum(float(i["price"]) * int(i["quantity"]) for i in items)
    return {"products": len(items), "total": round(total, 2)}


def handler(event, context):
    # HttpApi events carry the payload in "body"; direct invocations pass it as the event.
    if isinstance(event, dict) and "body" in event:
        event = json.loads(event["body"] or "{}")

    begin = time.time()
    cart_id = event.get("cart_id") or str(uuid.uuid4())
    results = []
    for request in event.get("requests", []):
        route = request["route"]
        body = request.get("body", {})
        if route == "PUT /cart":
            add_product(cart_id, body["product_id"], body["name"], body["price"], body["quantity"])
            results.append({"route": route, "ok": True})
        elif route == "GET /cart/{id}":
            item = get_product(cart_id, body["product_id"])
            results.append({"route": route, "found": item is not None})
        elif route == "GET /cart":
            results.append({"route": route, **query_cart(cart_id)})
        else:
            raise ValueError(f"unknown route {route}")

    return {
        "statusCode": 200,
        "body": json.dumps({"cart_id": cart_id, "results": results,
                            "compute_time_us": int((time.time() - begin) * 1e6)}),
    }
