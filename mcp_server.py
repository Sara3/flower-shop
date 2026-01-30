"""
UCP Flower Shop MCP Server (HTTP/SSE Transport)

Standalone MCP server with built-in mock flower shop data.
No external backend required - works as a complete demo.

Run:
  python mcp_server.py
  
Connect via: http://localhost:8000/sse
"""

import json
import uuid
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import os


# ============ MOCK DATA ============
MOCK_PRODUCTS = {
    "bouquet_roses": {
        "id": "bouquet_roses",
        "title": "Bouquet of Red Roses",
        "description": "A stunning arrangement of 12 fresh red roses, perfect for any romantic occasion.",
        "price": {"amount": 35.00, "currency": "USD"},
        "image_url": "https://example.com/roses.jpg",
        "in_stock": True
    },
    "orchid_white": {
        "id": "orchid_white",
        "title": "White Phalaenopsis Orchid",
        "description": "Elegant potted white orchid, long-lasting and easy to care for.",
        "price": {"amount": 45.00, "currency": "USD"},
        "image_url": "https://example.com/orchid.jpg",
        "in_stock": True
    },
    "tulips_mixed": {
        "id": "tulips_mixed",
        "title": "Mixed Tulip Bouquet",
        "description": "Cheerful mix of 15 colorful tulips in spring colors.",
        "price": {"amount": 28.00, "currency": "USD"},
        "image_url": "https://example.com/tulips.jpg",
        "in_stock": True
    },
    "succulent_trio": {
        "id": "succulent_trio",
        "title": "Succulent Trio",
        "description": "Three adorable succulents in decorative pots. Low maintenance, high style.",
        "price": {"amount": 22.00, "currency": "USD"},
        "image_url": "https://example.com/succulents.jpg",
        "in_stock": True
    },
    "sunflower_bunch": {
        "id": "sunflower_bunch",
        "title": "Sunflower Sunshine Bunch",
        "description": "Bright and cheerful bunch of 6 large sunflowers.",
        "price": {"amount": 25.00, "currency": "USD"},
        "image_url": "https://example.com/sunflowers.jpg",
        "in_stock": True
    },
    "lily_bouquet": {
        "id": "lily_bouquet",
        "title": "Stargazer Lily Bouquet",
        "description": "Fragrant pink stargazer lilies with eucalyptus accents.",
        "price": {"amount": 42.00, "currency": "USD"},
        "image_url": "https://example.com/lilies.jpg",
        "in_stock": True
    },
    "pothos_golden": {
        "id": "pothos_golden",
        "title": "Golden Pothos Plant",
        "description": "Easy-care trailing plant, perfect for beginners. Comes in a 6-inch pot.",
        "price": {"amount": 18.00, "currency": "USD"},
        "image_url": "https://example.com/pothos.jpg",
        "in_stock": True
    },
    "peace_lily": {
        "id": "peace_lily",
        "title": "Peace Lily",
        "description": "Classic indoor plant with elegant white blooms. Air-purifying.",
        "price": {"amount": 32.00, "currency": "USD"},
        "image_url": "https://example.com/peace_lily.jpg",
        "in_stock": True
    }
}

MOCK_DISCOVERY = {
    "ucp": {
        "version": "2026-01-11",
        "services": {
            "dev.ucp.shopping": {
                "version": "2026-01-11",
                "spec": "https://ucp.dev/specs/shopping",
                "rest": {
                    "schema": "https://ucp.dev/services/shopping/openapi.json",
                    "endpoint": "https://flower-shop.example.com/"
                }
            }
        },
        "capabilities": [
            {
                "name": "dev.ucp.shopping.checkout",
                "version": "2026-01-11",
                "spec": "https://ucp.dev/specs/shopping/checkout"
            },
            {
                "name": "dev.ucp.shopping.discount",
                "version": "2026-01-11",
                "spec": "https://ucp.dev/specs/shopping/discount",
                "extends": "dev.ucp.shopping.checkout"
            },
            {
                "name": "dev.ucp.shopping.fulfillment",
                "version": "2026-01-11",
                "spec": "https://ucp.dev/specs/shopping/fulfillment",
                "extends": "dev.ucp.shopping.checkout"
            }
        ]
    },
    "payment": {
        "handlers": [
            {
                "id": "mock_payment",
                "name": "dev.ucp.mock_payment",
                "version": "2026-01-11",
                "config": {"supported_tokens": ["sandbox_test", "success_token"]}
            }
        ]
    }
}

DISCOUNT_CODES = {
    "10OFF": {"title": "10% Off", "percent": 10},
    "FLOWERS20": {"title": "20% Off Flowers", "percent": 20},
    "FREESHIP": {"title": "Free Shipping", "amount": 5.99}
}

# In-memory stores
checkouts: dict[str, dict] = {}
orders: dict[str, dict] = {}


# ============ MOCK UCP FUNCTIONS ============
def mock_discover() -> dict:
    return MOCK_DISCOVERY


def mock_list_products() -> list[dict]:
    return list(MOCK_PRODUCTS.values())


def mock_get_product(product_id: str) -> dict | None:
    return MOCK_PRODUCTS.get(product_id)


def mock_create_checkout(
    line_items: list[dict],
    buyer: dict | None = None,
    currency: str = "USD"
) -> dict:
    checkout_id = str(uuid.uuid4())
    
    # Calculate line item totals
    processed_items = []
    subtotal = 0
    
    for item in line_items:
        product_id = item.get("item", {}).get("id")
        quantity = item.get("quantity", 1)
        product = MOCK_PRODUCTS.get(product_id)
        
        if product:
            item_total = product["price"]["amount"] * quantity
            subtotal += item_total
            processed_items.append({
                "id": str(uuid.uuid4()),
                "item": {
                    "id": product_id,
                    "title": product["title"],
                    "price": product["price"]["amount"]
                },
                "quantity": quantity,
                "totals": [
                    {"type": "subtotal", "amount": item_total},
                    {"type": "total", "amount": item_total}
                ]
            })
    
    checkout = {
        "id": checkout_id,
        "status": "pending",
        "currency": currency,
        "line_items": processed_items,
        "buyer": buyer or {},
        "totals": [
            {"type": "subtotal", "amount": subtotal},
            {"type": "total", "amount": subtotal}
        ],
        "discounts": {"codes": [], "applied": []},
        "fulfillment": None,
        "created_at": datetime.utcnow().isoformat()
    }
    
    checkouts[checkout_id] = checkout
    return checkout


def mock_get_checkout(checkout_id: str) -> dict | None:
    return checkouts.get(checkout_id)


def mock_update_checkout(checkout_id: str, updates: dict) -> dict | None:
    checkout = checkouts.get(checkout_id)
    if not checkout:
        return None
    
    # Handle fulfillment/shipping
    if "fulfillment" in updates:
        checkout["fulfillment"] = updates["fulfillment"]
        # Add shipping cost
        shipping_cost = 5.99
        totals = checkout["totals"]
        subtotal = next((t["amount"] for t in totals if t["type"] == "subtotal"), 0)
        discount = next((t["amount"] for t in totals if t["type"] == "discount"), 0)
        checkout["totals"] = [
            {"type": "subtotal", "amount": subtotal},
            {"type": "shipping", "amount": shipping_cost},
            {"type": "discount", "amount": discount} if discount else None,
            {"type": "total", "amount": subtotal + shipping_cost - discount}
        ]
        checkout["totals"] = [t for t in checkout["totals"] if t]
    
    # Handle discount codes
    if "discount" in updates:
        codes = updates["discount"].get("codes", [])
        applied = []
        total_discount = 0
        subtotal = next((t["amount"] for t in checkout["totals"] if t["type"] == "subtotal"), 0)
        
        for code in codes:
            if code.upper() in DISCOUNT_CODES:
                disc = DISCOUNT_CODES[code.upper()]
                if "percent" in disc:
                    amount = subtotal * disc["percent"] / 100
                else:
                    amount = disc.get("amount", 0)
                total_discount += amount
                applied.append({
                    "code": code.upper(),
                    "title": disc["title"],
                    "amount": amount
                })
        
        checkout["discounts"] = {"codes": codes, "applied": applied}
        
        # Recalculate totals
        shipping = next((t["amount"] for t in checkout["totals"] if t["type"] == "shipping"), 0)
        checkout["totals"] = [
            {"type": "subtotal", "amount": subtotal},
            {"type": "shipping", "amount": shipping} if shipping else None,
            {"type": "discount", "amount": total_discount} if total_discount else None,
            {"type": "total", "amount": subtotal + shipping - total_discount}
        ]
        checkout["totals"] = [t for t in checkout["totals"] if t]
    
    checkout["status"] = "ready_for_complete"
    return checkout


def mock_submit_checkout(checkout_id: str, payment: dict | None = None) -> dict | None:
    checkout = checkouts.get(checkout_id)
    if not checkout:
        return None
    
    order_id = f"ORD-{str(uuid.uuid4())[:8].upper()}"
    
    order = {
        "id": order_id,
        "status": "confirmed",
        "checkout_id": checkout_id,
        "line_items": checkout["line_items"],
        "buyer": checkout["buyer"],
        "totals": checkout["totals"],
        "fulfillment": checkout["fulfillment"],
        "payment": {
            "status": "captured",
            "method": "mock_payment"
        },
        "created_at": datetime.utcnow().isoformat()
    }
    
    orders[order_id] = order
    checkout["status"] = "completed"
    checkout["order_id"] = order_id
    
    return order


def mock_get_order(order_id: str) -> dict | None:
    return orders.get(order_id)


def mock_list_orders() -> list[dict]:
    return list(orders.values())


# ============ MCP SERVER ============
server = Server("ucp-flower-shop")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ucp_discover",
            description="Discover merchant capabilities via UCP. Returns supported services, capabilities, and payment handlers.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="ucp_list_products",
            description="List all available products from the flower shop catalog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_price": {
                        "type": "number",
                        "description": "Optional: Filter products by maximum price"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="ucp_get_product",
            description="Get detailed information about a specific product by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID (e.g., 'bouquet_roses', 'orchid_white', 'pothos_golden')"
                    }
                },
                "required": ["product_id"]
            }
        ),
        Tool(
            name="ucp_create_checkout",
            description="Create a new checkout session with line items. Returns checkout_id for subsequent operations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID to purchase"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to purchase (default: 1)",
                        "default": 1
                    },
                    "buyer_name": {
                        "type": "string",
                        "description": "Buyer's full name"
                    },
                    "buyer_email": {
                        "type": "string",
                        "description": "Buyer's email address"
                    }
                },
                "required": ["product_id"]
            }
        ),
        Tool(
            name="ucp_get_checkout",
            description="Get current state of a checkout session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkout_id": {
                        "type": "string",
                        "description": "The checkout session ID"
                    }
                },
                "required": ["checkout_id"]
            }
        ),
        Tool(
            name="ucp_update_checkout",
            description="Update a checkout session with shipping address or discount code. Available codes: 10OFF, FLOWERS20, FREESHIP",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkout_id": {
                        "type": "string",
                        "description": "The checkout session ID"
                    },
                    "shipping_address": {
                        "type": "object",
                        "description": "Shipping address object",
                        "properties": {
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "address1": {"type": "string"},
                            "city": {"type": "string"},
                            "province": {"type": "string"},
                            "postal_code": {"type": "string"},
                            "country": {"type": "string", "default": "US"}
                        }
                    },
                    "discount_code": {
                        "type": "string",
                        "description": "Discount code to apply (e.g., '10OFF', 'FLOWERS20', 'FREESHIP')"
                    }
                },
                "required": ["checkout_id"]
            }
        ),
        Tool(
            name="ucp_submit_checkout",
            description="Submit/complete the checkout to create an order. This finalizes the purchase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkout_id": {
                        "type": "string",
                        "description": "The checkout session ID to submit"
                    },
                    "payment_token": {
                        "type": "string",
                        "description": "Payment token (use 'sandbox_test' for demo)",
                        "default": "sandbox_test"
                    }
                },
                "required": ["checkout_id"]
            }
        ),
        Tool(
            name="ucp_get_order",
            description="Get details of a completed order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID"
                    }
                },
                "required": ["order_id"]
            }
        ),
        Tool(
            name="ucp_list_orders",
            description="List all orders.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "ucp_discover":
            result = mock_discover()
            return [TextContent(
                type="text",
                text=f"UCP Discovery Profile:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_list_products":
            products = mock_list_products()
            max_price = arguments.get("max_price")
            
            if max_price:
                products = [p for p in products if p.get("price", {}).get("amount", 0) <= max_price]
            
            if not products:
                return [TextContent(type="text", text="No products found.")]
            
            result = "🌸 **Flower Shop Catalog**\n\n"
            for p in products:
                price = p.get("price", {})
                amount = price.get("amount", 0)
                currency = price.get("currency", "USD")
                result += f"**{p.get('title', 'Unknown')}** - ${amount:.2f} {currency}\n"
                result += f"  ID: `{p.get('id')}`\n"
                if p.get("description"):
                    result += f"  _{p.get('description')}_\n"
                result += "\n"
            
            return [TextContent(type="text", text=result)]
        
        elif name == "ucp_get_product":
            product = mock_get_product(arguments["product_id"])
            if not product:
                return [TextContent(type="text", text=f"❌ Product not found: {arguments['product_id']}")]
            return [TextContent(
                type="text",
                text=f"Product Details:\n\n```json\n{json.dumps(product, indent=2)}\n```"
            )]
        
        elif name == "ucp_create_checkout":
            line_items = [{
                "item": {"id": arguments["product_id"]},
                "quantity": arguments.get("quantity", 1)
            }]
            
            buyer = None
            if arguments.get("buyer_name") or arguments.get("buyer_email"):
                buyer = {
                    "full_name": arguments.get("buyer_name", ""),
                    "email": arguments.get("buyer_email", "")
                }
            
            result = mock_create_checkout(line_items, buyer)
            checkout_id = result.get("id")
            
            return [TextContent(
                type="text",
                text=f"✅ Checkout created!\n\nCheckout ID: `{checkout_id}`\n\nNext steps:\n1. Use `ucp_update_checkout` to add shipping address\n2. Use `ucp_submit_checkout` to complete purchase\n\nFull response:\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_get_checkout":
            result = mock_get_checkout(arguments["checkout_id"])
            if not result:
                return [TextContent(type="text", text=f"❌ Checkout not found: {arguments['checkout_id']}")]
            return [TextContent(
                type="text",
                text=f"Checkout Session:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_update_checkout":
            updates = {}
            
            if arguments.get("shipping_address"):
                updates["fulfillment"] = {
                    "expectations": [{
                        "method_type": "shipping",
                        "destination": arguments["shipping_address"]
                    }]
                }
            
            if arguments.get("discount_code"):
                updates["discount"] = {
                    "codes": [arguments["discount_code"]]
                }
            
            result = mock_update_checkout(arguments["checkout_id"], updates)
            if not result:
                return [TextContent(type="text", text=f"❌ Checkout not found: {arguments['checkout_id']}")]
            return [TextContent(
                type="text",
                text=f"✅ Checkout updated!\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_submit_checkout":
            payment = {
                "instruments": [{
                    "type": "token",
                    "token": arguments.get("payment_token", "sandbox_test")
                }]
            }
            
            result = mock_submit_checkout(arguments["checkout_id"], payment)
            if not result:
                return [TextContent(type="text", text=f"❌ Checkout not found: {arguments['checkout_id']}")]
            order_id = result.get("id")
            
            return [TextContent(
                type="text",
                text=f"🎉 Order Complete!\n\nOrder ID: `{order_id}`\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_get_order":
            result = mock_get_order(arguments["order_id"])
            if not result:
                return [TextContent(type="text", text=f"❌ Order not found: {arguments['order_id']}")]
            return [TextContent(
                type="text",
                text=f"Order Details:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_list_orders":
            result = mock_list_orders()
            if not result:
                return [TextContent(type="text", text="No orders yet.")]
            return [TextContent(
                type="text",
                text=f"Orders ({len(result)} total):\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Error: {type(e).__name__}: {e}")]


# ============ HTTP/SSE SERVER ============
sse_transport = SseServerTransport("/messages")


async def handle_sse(request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)


async def handle_health(request):
    return JSONResponse({"status": "ok", "server": "ucp-flower-shop"})


async def handle_info(request):
    return JSONResponse({
        "name": "ucp-flower-shop",
        "description": "UCP Flower Shop MCP Server - Standalone demo with mock data",
        "transport": "HTTP/SSE",
        "sse_endpoint": "/sse",
        "products": list(MOCK_PRODUCTS.keys()),
        "discount_codes": list(DISCOUNT_CODES.keys()),
        "tools": [
            "ucp_discover",
            "ucp_list_products",
            "ucp_get_product",
            "ucp_create_checkout",
            "ucp_get_checkout",
            "ucp_update_checkout",
            "ucp_submit_checkout",
            "ucp_get_order",
            "ucp_list_orders"
        ]
    })


app = Starlette(
    debug=True,
    routes=[
        Route("/health", handle_health),
        Route("/info", handle_info),
        Route("/sse", handle_sse),
        Route("/messages", handle_messages, methods=["POST"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║              🌸 UCP Flower Shop MCP Server                       ║
║                                                                  ║
║  SSE Endpoint:  http://localhost:{port}/sse                        ║
║  Health:        http://localhost:{port}/health                     ║
║  Info:          http://localhost:{port}/info                       ║
║                                                                  ║
║  Mode: STANDALONE (built-in mock data)                           ║
║                                                                  ║
║  Products:                                                       ║
║    • bouquet_roses    - $35.00                                   ║
║    • orchid_white     - $45.00                                   ║
║    • tulips_mixed     - $28.00                                   ║
║    • succulent_trio   - $22.00                                   ║
║    • sunflower_bunch  - $25.00                                   ║
║    • lily_bouquet     - $42.00                                   ║
║    • pothos_golden    - $18.00                                   ║
║    • peace_lily       - $32.00                                   ║
║                                                                  ║
║  Discount Codes: 10OFF, FLOWERS20, FREESHIP                      ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=port)
