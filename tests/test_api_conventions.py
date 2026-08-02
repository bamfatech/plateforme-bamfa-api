from rest_framework import exceptions

from apps.common.exceptions import bamfa_exception_handler
from apps.common.pagination import DefaultPagination


def test_pagination_par_defaut():
    p = DefaultPagination()
    assert p.page_size == 20
    assert p.page_size_query_param == "page_size"


def test_handler_erreur_validation():
    exc = exceptions.ValidationError({"email": ["Ce champ est requis."]})
    response = bamfa_exception_handler(exc, {})
    assert response is not None
    assert set(response.data["error"].keys()) == {"code", "message", "details"}
    assert response.data["error"]["details"] == {"email": ["Ce champ est requis."]}


def test_handler_erreur_authentification():
    exc = exceptions.NotAuthenticated()
    response = bamfa_exception_handler(exc, {})
    assert response.data["error"]["code"] == "not_authenticated"
    assert response.data["error"]["details"] == {}


def test_handler_ignore_les_exceptions_non_drf():
    assert bamfa_exception_handler(ValueError("boom"), {}) is None
