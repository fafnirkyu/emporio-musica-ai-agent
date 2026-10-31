import json
from decimal import Decimal, ROUND_HALF_UP


MAX_RESULTS = 10

PRODUCT_SELECT = """
SELECT
    p.product_id,
    p.name,
    p.description,
    p.price_cents,
    p.stock_quantity,
    p.status,
    p.specs_json,
    c.name AS category,
    promotion.promotion_id,
    promotion.description AS promotion_description,
    promotion.discount_percent
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
LEFT JOIN promotions AS promotion
    ON promotion.product_id = p.product_id
    AND promotion.is_active = 1
"""

AVAILABILITY_ORDER = """
CASE
    WHEN p.status = 'active' AND p.stock_quantity > 0 THEN 0
    WHEN p.status = 'active' AND p.stock_quantity = 0 THEN 1
    WHEN p.status = 'coming_soon' THEN 2
    WHEN p.status = 'discontinued' THEN 3
    ELSE 4
END
"""

CURRENT_PRICE = """
CASE
    WHEN promotion.discount_percent IS NOT NULL
    THEN CAST(
        (
            p.price_cents
            * (100 - promotion.discount_percent)
            + 50
        ) / 100 AS INTEGER
    )
    ELSE p.price_cents
END
"""

ORDER_STATUS_LABELS = {
    "pending": "Pendente",
    "confirmed": "Confirmado",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}


def search_products(
    connection,
    query=None,
    category=None,
    maximum_price_cents=None,
    limit=5,
):
    filters = []
    parameters = []

    if query:
        search_term = f"%{query.strip()}%"
        filters.append(
            """
            (
                LOWER(p.name) LIKE LOWER(?)
                OR LOWER(p.description) LIKE LOWER(?)
            )
            """
        )
        parameters.extend([search_term, search_term])

    if category:
        category_term = f"%{category.strip()}%"
        filters.append("LOWER(c.name) LIKE LOWER(?)")
        parameters.append(category_term)

    if maximum_price_cents is not None:
        maximum_price_cents = int(maximum_price_cents)

        if maximum_price_cents < 0:
            raise ValueError("Maximum price cannot be negative")

        filters.append(f"{CURRENT_PRICE} <= ?")
        parameters.append(maximum_price_cents)

    products = find_products(
        connection,
        filters=filters,
        parameters=parameters,
        limit=limit,
    )

    return {
        "count": len(products),
        "products": products,
    }


def get_product(connection, name):
    name = name.strip()

    if not name:
        return {
            "found": False,
            "message": "A product name is required.",
            "suggestions": [],
        }

    exact_matches = find_products(
        connection,
        filters=["LOWER(p.name) = LOWER(?)"],
        parameters=[name],
        limit=1,
    )

    if exact_matches:
        return {
            "found": True,
            "exact_match": True,
            "product": exact_matches[0],
        }

    suggestions = search_products(
        connection,
        query=name,
        limit=5,
    )["products"]

    return {
        "found": False,
        "message": "No exact product was found.",
        "suggestions": suggestions,
    }


def list_active_promotions(connection, limit=5):
    products = find_products(
        connection,
        filters=[
            "promotion.promotion_id IS NOT NULL",
            "p.status = 'active'",
            "p.stock_quantity > 0",
        ],
        parameters=[],
        limit=limit,
        order_by="promotion.discount_percent DESC, p.name",
    )

    return {
        "count": len(products),
        "products": products,
    }


def get_order_status(connection, order_id, email):
    email = email.strip()

    if not email:
        return order_not_verified()

    order = connection.execute(
        """
        SELECT
            o.order_id,
            o.order_date,
            o.status,
            o.total_cents,
            o.payment_method,
            o.tracking_code,
            o.estimated_delivery,
            o.notes
        FROM orders AS o
        JOIN customers AS c
            ON c.customer_id = o.customer_id
        WHERE
            o.order_id = ?
            AND LOWER(TRIM(c.email)) = LOWER(TRIM(?))
        """,
        (int(order_id), email),
    ).fetchone()

    if order is None:
        return order_not_verified()

    items = connection.execute(
        """
        SELECT
            item.product_id,
            product.name,
            item.quantity
        FROM order_items AS item
        JOIN products AS product
            ON product.product_id = item.product_id
        WHERE item.order_id = ?
        ORDER BY product.name
        """,
        (order["order_id"],),
    ).fetchall()

    return {
        "verified": True,
        "order": {
            "order_id": order["order_id"],
            "order_date": order["order_date"],
            "status": order["status"],
            "status_label": ORDER_STATUS_LABELS.get(
                order["status"],
                order["status"],
            ),
            "total_cents": order["total_cents"],
            "total_brl": format_brl(order["total_cents"]),
            "payment_method": order["payment_method"],
            "tracking_code": order["tracking_code"],
            "estimated_delivery": order["estimated_delivery"],
            "notes": order["notes"],
            "items": [
                {
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "quantity": item["quantity"],
                }
                for item in items
            ],
        },
    }


def find_products(
    connection,
    filters,
    parameters,
    limit,
    order_by=None,
):
    limit = normalize_limit(limit)
    where_clause = " AND ".join(filters) if filters else "1 = 1"
    ordering = order_by or f"{AVAILABILITY_ORDER}, p.name"

    query = f"""
    {PRODUCT_SELECT}
    WHERE {where_clause}
    ORDER BY {ordering}
    LIMIT ?
    """

    rows = connection.execute(
        query,
        [*parameters, limit],
    ).fetchall()

    return [product_from_row(row) for row in rows]


def product_from_row(row):
    available, availability, warning = product_availability(
        status=row["status"],
        stock_quantity=row["stock_quantity"],
    )

    discount_percent = row["discount_percent"]
    current_price_cents = row["price_cents"]

    if discount_percent is not None:
        current_price_cents = discounted_price(
            price_cents=row["price_cents"],
            discount_percent=discount_percent,
        )

    display_name = row["name"]

    if warning:
        display_name = f"{warning} {display_name}"

    promotion = None

    if row["promotion_id"] is not None:
        promotion = {
            "promotion_id": row["promotion_id"],
            "description": row["promotion_description"],
            "discount_percent": discount_percent,
        }

    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "display_name": display_name,
        "description": row["description"],
        "category": row["category"],
        "status": row["status"],
        "availability": availability,
        "available": available,
        "stock_quantity": row["stock_quantity"],
        "original_price_cents": row["price_cents"],
        "original_price_brl": format_brl(row["price_cents"]),
        "current_price_cents": current_price_cents,
        "current_price_brl": format_brl(current_price_cents),
        "promotion": promotion,
        "specs": json.loads(row["specs_json"]),
    }


def product_availability(status, stock_quantity):
    if status == "active" and stock_quantity > 0:
        return True, "available", ""

    if status == "active":
        return False, "out_of_stock", "[SEM ESTOQUE]"

    if status == "coming_soon":
        return False, "coming_soon", "[EM BREVE]"

    if status == "discontinued":
        return False, "discontinued", "[DESCONTINUADO]"

    return False, "unavailable", "[INDISPONÍVEL]"


def discounted_price(price_cents, discount_percent):
    price = Decimal(price_cents)
    multiplier = Decimal(100 - discount_percent) / Decimal(100)

    return int(
        (price * multiplier).quantize(
            Decimal(1),
            rounding=ROUND_HALF_UP,
        )
    )


def format_brl(value_cents):
    value = Decimal(value_cents) / Decimal(100)
    formatted = f"{value:,.2f}"

    formatted = formatted.replace(",", "_")
    formatted = formatted.replace(".", ",")
    formatted = formatted.replace("_", ".")

    return f"R$ {formatted}"


def normalize_limit(limit):
    limit = int(limit)

    return max(1, min(limit, MAX_RESULTS))


def order_not_verified():
    return {
        "verified": False,
        "message": (
            "Order not found or the supplied email "
            "does not match the order."
        ),
    }