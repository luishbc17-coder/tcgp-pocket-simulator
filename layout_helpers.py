"""Pure pagination helpers used by the mobile/desktop card gallery."""
from math import ceil

PAGE_SIZE = 24


def paginate(items, requested_page, page_size=PAGE_SIZE):
    """Return (page_items, page, pages) with bounds checked.

    ``items`` can be a list or another finite sequence. Empty results
    intentionally use page 1 of 1 so navigation widgets remain valid.
    """
    if type(requested_page) is not int:
        raise ValueError('A página precisa ser um inteiro.')
    if type(page_size) is not int or page_size < 1:
        raise ValueError('O tamanho de página precisa ser positivo.')
    pages = max(1, ceil(len(items) / page_size))
    page = max(1, min(requested_page, pages))
    return items[(page - 1) * page_size : page * page_size], page, pages
