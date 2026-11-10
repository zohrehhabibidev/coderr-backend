from rest_framework.pagination import PageNumberPagination


class OfferPagination(PageNumberPagination):
    """List-only pagination; size defaults are implementation decisions."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
