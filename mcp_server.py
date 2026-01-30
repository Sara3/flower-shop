"""
UCP Flower Shop MCP Server (HTTP/SSE Transport)

Wraps the UCP REST API as MCP tools for Claude Desktop / MCP Inspector / Playground.

Run UCP flower shop first:
  cd samples/rest/python/server
  uv run server.py --port=8182 --products_db_path=/tmp/ucp/products.db --transactions_db_path=/tmp/ucp/transactions.db

Then run this MCP server:
  python mcp_server.py
  
Connect via: http://localhost:8000/sse
"""

import json
import httpx
import uuid
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import os


# ============ CONFIG ============
UCP_BASE_URL = os.environ.get("UCP_BASE_URL", "http://localhost:8182")


# ============ UCP REST CLIENT ============
class UCPClient:
    """Wraps UCP REST API calls"""
    
    def __init__(self, base_url: str = UCP_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def _headers(self) -> dict:
        """Standard UCP headers"""
        return {
            "Content-Type": "application/json",
            "UCP-Agent": 'profile="https://mcp.example/agent"',
            "request-signature": "test",
            "idempotency-key": str(uuid.uuid4()),
            "request-id": str(uuid.uuid4()),
        }
    
    async def discover(self) -> dict:
        """GET /.well-known/ucp - Discover merchant capabilities"""
        resp = await self.client.get(f"{self.base_url}/.well-known/ucp")
        resp.raise_for_status()
        return resp.json()
    
    async def list_products(self) -> list[dict]:
        """GET /products - List available products"""
        resp = await self.client.get(
            f"{self.base_url}/products",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()
    
    async def get_product(self, product_id: str) -> dict:
        """GET /products/{id} - Get product details"""
        resp = await self.client.get(
            f"{self.base_url}/products/{product_id}",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()
    
    async def create_checkout(
        self,
        line_items: list[dict],
        buyer: dict | None = None,
        currency: str = "USD"
    ) -> dict:
        """POST /checkout-sessions - Create a checkout session"""
        payload = {
            "line_items": line_items,
            "currency": currency,
        }
        if buyer:
            payload["buyer"] = buyer
            
        resp = await self.client.post(
            f"{self.base_url}/checkout-sessions",
            headers=self._headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()
    
    async def get_checkout(self, checkout_id: str) -> dict:
        """GET /checkout-sessions/{id} - Get checkout session"""
        resp = await self.client.get(
            f"{self.base_url}/checkout-sessions/{checkout_id}",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()
    
    async def update_checkout(
        self,
        checkout_id: str,
        updates: dict
    ) -> dict:
        """PATCH /checkout-sessions/{id} - Update checkout (add shipping, discounts, etc)"""
        resp = await self.client.patch(
            f"{self.base_url}/checkout-sessions/{checkout_id}",
            headers=self._headers(),
            json=updates
        )
        resp.raise_for_status()
        return resp.json()
    
    async def submit_checkout(
        self,
        checkout_id: str,
        payment: dict | None = None
    ) -> dict:
        """POST /checkout-sessions/{id}/submit - Complete the purchase"""
        payload = {}
        if payment:
            payload["payment"] = payment
            
        resp = await self.client.post(
            f"{self.base_url}/checkout-sessions/{checkout_id}/submit",
            headers=self._headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()
    
    async def get_order(self, order_id: str) -> dict:
        """GET /orders/{id} - Get order details"""
        resp = await self.client.get(
            f"{self.base_url}/orders/{order_id}",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()
    
    async def list_orders(self) -> list[dict]:
        """GET /orders - List orders"""
        resp = await self.client.get(
            f"{self.base_url}/orders",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()


ucp = UCPClient()


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
                        "description": "The product ID (e.g., 'bouquet_roses')"
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
            description="Update a checkout session with shipping address or other details.",
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
                        "description": "Optional discount code to apply"
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
            result = await ucp.discover()
            return [TextContent(
                type="text",
                text=f"UCP Discovery Profile:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_list_products":
            products = await ucp.list_products()
            max_price = arguments.get("max_price")
            
            if max_price:
                products = [p for p in products if p.get("price", {}).get("amount", 0) <= max_price]
            
            if not products:
                return [TextContent(type="text", text="No products found.")]
            
            result = "🌸 Available Products:\n\n"
            for p in products:
                price = p.get("price", {})
                amount = price.get("amount", 0)
                currency = price.get("currency", "USD")
                result += f"**{p.get('title', 'Unknown')}** - ${amount:.2f} {currency}\n"
                result += f"  ID: `{p.get('id')}`\n"
                if p.get("description"):
                    result += f"  {p.get('description')}\n"
                result += "\n"
            
            return [TextContent(type="text", text=result)]
        
        elif name == "ucp_get_product":
            product = await ucp.get_product(arguments["product_id"])
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
            
            result = await ucp.create_checkout(line_items, buyer)
            checkout_id = result.get("id") or result.get("checkout_id")
            
            return [TextContent(
                type="text",
                text=f"✅ Checkout created!\n\nCheckout ID: `{checkout_id}`\n\nNext steps:\n1. Use `ucp_update_checkout` to add shipping address\n2. Use `ucp_submit_checkout` to complete purchase\n\nFull response:\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_get_checkout":
            result = await ucp.get_checkout(arguments["checkout_id"])
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
            
            result = await ucp.update_checkout(arguments["checkout_id"], updates)
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
            
            result = await ucp.submit_checkout(arguments["checkout_id"], payment)
            order_id = result.get("id") or result.get("order_id")
            
            return [TextContent(
                type="text",
                text=f"🎉 Order Complete!\n\nOrder ID: `{order_id}`\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_get_order":
            result = await ucp.get_order(arguments["order_id"])
            return [TextContent(
                type="text",
                text=f"Order Details:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_list_orders":
            result = await ucp.list_orders()
            return [TextContent(
                type="text",
                text=f"Orders:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"❌ UCP API Error: {e.response.status_code}\n\n{e.response.text}"
        )]
    except httpx.ConnectError:
        return [TextContent(
            type="text",
            text=f"❌ Cannot connect to UCP server at {UCP_BASE_URL}\n\nMake sure the flower shop server is running:\n```\ncd samples/rest/python/server\nuv run server.py --port=8182 ...\n```"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Error: {type(e).__name__}: {e}")]


# ============ HTTP/SSE SERVER ============
def create_app():
    sse = SseServerTransport("/messages/")
    
    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
    
    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)
    
    async def handle_health(request):
        return JSONResponse({"status": "ok", "server": "ucp-flower-shop"})
    
    async def handle_info(request):
        return JSONResponse({
            "name": "ucp-flower-shop",
            "description": "MCP Server wrapping UCP Flower Shop REST API",
            "ucp_endpoint": UCP_BASE_URL,
            "transport": "HTTP/SSE",
            "sse_endpoint": "/sse",
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
    
    return Starlette(
        debug=True,
        routes=[
            Route("/health", handle_health),
            Route("/info", handle_info),
            Route("/sse", handle_sse),
            Route("/messages/", handle_messages, methods=["POST"]),
        ]
    )


app = create_app()


if __name__ == "__main__":
    import os
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
║  UCP Backend:   {UCP_BASE_URL}                            ║
║                                                                  ║
║  Tools:                                                          ║
║    • ucp_discover        - Get merchant capabilities             ║
║    • ucp_list_products   - Browse flower catalog                 ║
║    • ucp_get_product     - Get product details                   ║
║    • ucp_create_checkout - Start checkout session                ║
║    • ucp_get_checkout    - View checkout state                   ║
║    • ucp_update_checkout - Add shipping/discounts                ║
║    • ucp_submit_checkout - Complete purchase                     ║
║    • ucp_get_order       - View order details                    ║
║    • ucp_list_orders     - List all orders                       ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=port)
