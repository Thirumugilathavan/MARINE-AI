import copernicusmarine


def search_catalogue(keyword: str, limit: int = 10):
    """
    Search the Copernicus Marine catalogue.

    Args:
        keyword: Search term, such as thetao, salinity, or chlorophyll.
        limit: Maximum number of products to return.

    Returns:
        A list of catalogue products.
    """

    result = copernicusmarine.describe(
        contains=[keyword],
        disable_progress_bar=True,
    )

    products = []

    for product in result.products[:limit]:
        products.append(
            {
                "product_id": product.product_id,
                "title": product.title,
            }
        )

    return {
        "provider": "Copernicus Marine",
        "query": keyword,
        "total_found": len(result.products),
        "returned": len(products),
        "products": products,
    }