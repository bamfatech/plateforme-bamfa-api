from django.conf import settings


def _common_kwargs():
    return {
        "httponly": settings.AUTH_COOKIE_HTTP_ONLY,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
    }


def set_auth_cookies(response, access, refresh):
    response.set_cookie(settings.AUTH_COOKIE, str(access), **_common_kwargs())
    response.set_cookie(settings.AUTH_COOKIE_REFRESH, str(refresh), **_common_kwargs())
    return response


def clear_auth_cookies(response):
    response.delete_cookie(settings.AUTH_COOKIE, path=settings.AUTH_COOKIE_PATH)
    response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path=settings.AUTH_COOKIE_PATH)
    return response
