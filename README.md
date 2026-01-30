# UCP Flower Shop MCP Server

MCP server with HTTP/SSE transport that wraps the UCP (Universal Commerce Protocol) flower shop REST API.

## Quick Start

### 1. Start UCP Flower Shop (Terminal 1)

```bash
# Clone UCP repos
git clone https://github.com/Universal-Commerce-Protocol/python-sdk.git sdk/python
git clone https://github.com/Universal-Commerce-Protocol/samples.git

# Setup SDK
cd sdk/python && uv sync && cd ../..

# Setup & run flower shop
cd samples/rest/python/server
uv sync

# Create database
mkdir -p /tmp/ucp
uv run import_csv.py \
    --products_db_path=/tmp/ucp/products.db \
    --transactions_db_path=/tmp/ucp/transactions.db \
    --data_dir=../../../../conformance/test_data/flower_shop

# Start server on port 8182
uv run server.py \
    --port=8182 \
    --products_db_path=/tmp/ucp/products.db \
    --transactions_db_path=/tmp/ucp/transactions.db
```

### 2. Start MCP Server (Terminal 2)

```bash
pip install -r requirements.txt
python mcp_server.py
```

### 3. Connect via MCP Playground

SSE Endpoint: `http://localhost:8000/sse`

## Tools

| Tool | Description |
|------|-------------|
| `ucp_discover` | Get merchant UCP capabilities |
| `ucp_list_products` | Browse flower catalog |
| `ucp_get_product` | Get product details |
| `ucp_create_checkout` | Start checkout session |
| `ucp_get_checkout` | View checkout state |
| `ucp_update_checkout` | Add shipping address |
| `ucp_submit_checkout` | Complete purchase |
| `ucp_get_order` | View order |
| `ucp_list_orders` | List all orders |

## Demo Flow

```
1. ucp_discover → See capabilities
2. ucp_list_products → Browse flowers
3. ucp_create_checkout(product_id="bouquet_roses") → Start checkout
4. ucp_update_checkout(checkout_id="...", shipping_address={...}) → Add shipping
5. ucp_submit_checkout(checkout_id="...") → Complete order
```

## Architecture

```
┌─────────────────┐     HTTP/SSE      ┌─────────────────┐     REST      ┌─────────────────┐
│  MCP Client     │ ◄──────────────► │  MCP Server     │ ◄───────────► │  UCP Flower     │
│  (Playground)   │                   │  :8000          │               │  Shop :8182     │
└─────────────────┘                   └─────────────────┘               └─────────────────┘
```
