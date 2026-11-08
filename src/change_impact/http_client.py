"""Bounded provider requests that do not forward credentials through redirects."""

from urllib.request import HTTPRedirectHandler, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def open_request(request, timeout=120):
    return build_opener(NoRedirects()).open(request, timeout=timeout)
