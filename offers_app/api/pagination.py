from rest_framework.pagination import PageNumberPagination


class OfferPagination(PageNumberPagination):
    """List pagination; size defaults are implementation choices."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
