"""
Odoo XML-RPC client for creating products and sale orders.
Uses XML-RPC because it's the most stable and well-documented Odoo API.
Compatible with Odoo 16, 17, and 18.
"""
import xmlrpc.client
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class OdooClient:
    """
    Handles all Odoo operations via XML-RPC:
    - Product creation (product.product / product.template)
    - Sale Order creation (sale.order)
    - Partner lookup (res.partner)
    """

    def __init__(self, url: str, db: str, username: str, api_key: str):
        self.url = url
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = None
        self.models = None
        self._product_cache: Dict[str, int] = {}  # sku -> product_id
        self._partner_cache: Dict[str, int] = {}   # name -> partner_id

    def connect(self):
        """Authenticate and get uid."""
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        version = common.version()
        logger.info(f"Connected to Odoo {version.get('server_version', 'unknown')}")

        self.uid = common.authenticate(self.db, self.username, self.api_key, {})
        if not self.uid:
            raise ConnectionError("Failed to authenticate with Odoo. Check credentials.")
        logger.info(f"Authenticated as UID={self.uid}")

        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def _execute(self, model: str, method: str, *args, **kwargs):
        """Execute an Odoo model method."""
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, model, method, *args, **kwargs
        )

    # ——— Partner (Dropshipper/Client) ————————————————————————

    def find_or_create_partner(self, name: str, vat: str = "", email: str = "") -> int:
        """
        Find a partner by name, or create if not exists.
        Partners are created as companies (is_company=True).
        Returns the res.partner ID.
        """
        if name in self._partner_cache:
            return self._partner_cache[name]

        partner_ids = self._execute(
            "res.partner", "search",
            [[["name", "=", name], ["is_company", "=", True]]],
        )

        if partner_ids:
            partner_id = partner_ids[0]
            logger.info(f"Found partner: {name} (ID={partner_id})")
        else:
            partner_vals = {
                "name": name,
                "is_company": True,
                "customer_rank": 1,
            }
            if vat:
                partner_vals["vat"] = vat
            if email:
                partner_vals["email"] = email

            partner_id = self._execute("res.partner", "create", [partner_vals])
            logger.info(f"Created partner: {name} (ID={partner_id})")

        self._partner_cache[name] = partner_id
        return partner_id

    # ——— Products ——————————————————————————————————————————

    def find_or_create_product(
        self,
        sku: str,
        name: str,
        cost: float = 0.0,
        weight: float = 0.0,
        hs_code: str = "",
        brand: str = "",
        category_name: str = "",
    ) -> int:
        """
        Find a product by SKU (default_code), or create if not exists.
        Products are created as MTO (Make to Order).
        The brand field stores the client/dropshipper name.
        Returns the product.product ID.
        """
        cache_key = f"{sku}:{brand}"
        if cache_key in self._product_cache:
            return self._product_cache[cache_key]

        product_ids = self._execute(
            "product.product", "search",
            [[["default_code", "=", sku]]],
        )

        if product_ids:
            product_id = product_ids[0]
            logger.info(f"Found product: {sku} (ID={product_id})")
            self._product_cache[cache_key] = product_id
            return product_id

        # Create new product
        product_vals = {
            "name": name,
            "default_code": sku,
            "type": "consu",  # Consumable (MTO)
            "sale_ok": True,
            "purchase_ok": False,
            "list_price": cost,
            "weight": weight,
        }
        if hs_code:
            product_vals["hs_code"] = hs_code

        # Try to set brand field (x_studio_brand or x_brand)
        if brand:
            try:
                product_vals["x_studio_brand"] = brand
                product_id = self._execute("product.product", "create", [product_vals])
                logger.info(f"Created product with brand: {sku} (ID={product_id})")
            except Exception:
                del product_vals["x_studio_brand"]
                try:
                    product_vals["x_brand"] = brand
                    product_id = self._execute("product.product", "create", [product_vals])
                    logger.info(f"Created product with x_brand: {sku} (ID={product_id})")
                except Exception:
                    if "x_brand" in product_vals:
                        del product_vals["x_brand"]
                    product_id = self._execute("product.product", "create", [product_vals])
                    logger.info(f"Created product (no brand field): {sku} (ID={product_id})")
        else:
            product_id = self._execute("product.product", "create", [product_vals])
            logger.info(f"Created product: {sku} (ID={product_id})")

        self._product_cache[cache_key] = product_id
        return product_id

    def find_logistics_products(self) -> Dict[str, int]:
        """
        Find the logistics service products that already exist in Odoo:
        - 'International Freight (Flete)': Costo logistico por peso (per kg) @ $6.50
        - 'Address Fee': Fee per address/order @ $8.00

        Returns dict with product IDs keyed by type:
            {"freight": product_id, "address_fee": product_id}

        Raises ValueError if products not found in Odoo.
        """
        products = {}

        # Search for International Freight product
        freight_ids = self._execute(
            "product.product", "search",
            [[["name", "ilike", "International Freight"]]],
        )
        if not freight_ids:
            # Fallback: search by partial name
            freight_ids = self._execute(
                "product.product", "search",
                [[["name", "ilike", "Flete"]]],
            )
        if not freight_ids:
            raise ValueError(
                "Product 'International Freight (Flete)' not found in Odoo. "
                "Please create it manually before running invoicing."
            )
        products["freight"] = freight_ids[0]

        # Read price to log it
        freight_data = self._execute(
            "product.product", "read",
            [freight_ids[:1], ["name", "list_price", "default_code"]],
        )
        logger.info(
            f"Found freight product: {freight_data[0]['name']} "
            f"(ID={freight_ids[0]}, price={freight_data[0]['list_price']})"
        )

        # Search for Address Fee product
        addr_ids = self._execute(
            "product.product", "search",
            [[["name", "ilike", "Address Fee"]]],
        )
        if not addr_ids:
            raise ValueError(
                "Product 'Address Fee' not found in Odoo. "
                "Please create it manually before running invoicing."
            )
        products["address_fee"] = addr_ids[0]

        addr_data = self._execute(
            "product.product", "read",
            [addr_ids[:1], ["name", "list_price", "default_code"]],
        )
        logger.info(
            f"Found address fee product: {addr_data[0]['name']} "
            f"(ID={addr_ids[0]}, price={addr_data[0]['list_price']})"
        )

        return products

    # ——— Sale Orders ——————————————————————————————————————

    def create_sale_order(
        self,
        partner_id: int,
        order_lines: List[Dict[str, Any]],
        reference: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        """
        Create a Sale Order (sale.order) in Odoo.

        Args:
            partner_id: Odoo partner ID (the dropshipper/client)
            order_lines: List of dicts with line items:
                - product_id (int): Odoo product ID
                - description (str): Line description
                - quantity (float): Quantity
                - price_unit (float): Unit price
            reference: Client reference text
            note: Internal notes

        Returns:
            Dict with 'id', 'name', 'amount_total', 'state' of the created SO
        """
        line_commands = []
        for line in order_lines:
            line_vals = {
                "product_id": line["product_id"],
                "name": line.get("description", ""),
                "product_uom_qty": line["quantity"],
                "price_unit": line["price_unit"],
            }
            line_commands.append((0, 0, line_vals))

        order_vals = {
            "partner_id": partner_id,
            "order_line": line_commands,
            "client_order_ref": reference,
            "note": note,
        }

        order_id = self._execute("sale.order", "create", [order_vals])

        # Read the SO details
        order_data = self._execute(
            "sale.order", "read",
            [[order_id], ["name", "amount_total", "state"]],
        )

        order_name = order_data[0]["name"] if order_data else f"SO-{order_id}"
        amount_total = order_data[0]["amount_total"] if order_data else 0
        state = order_data[0]["state"] if order_data else "draft"

        logger.info(
            f"Created Sale Order {order_name} (ID={order_id}) "
            f"for partner {partner_id}, total=${amount_total:.2f}, state={state}"
        )

        return {
            "id": order_id,
            "name": order_name,
            "amount_total": amount_total,
            "state": state,
        }

    def confirm_sale_order(self, order_id: int) -> bool:
        """
        Confirm a draft sale order (draft -> sale).
        Returns True if confirmed successfully.
        """
        try:
            self._execute("sale.order", "action_confirm", [[order_id]])
            logger.info(f"Confirmed sale order ID={order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to confirm SO {order_id}: {e}")
            return False
