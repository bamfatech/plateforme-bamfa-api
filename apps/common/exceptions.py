from rest_framework.views import exception_handler


def bamfa_exception_handler(exc, context):
    """Format d'erreur normalisé : {"error": {"code", "message", "details"}}.

    Enveloppe le handler DRF par défaut. Retourne None pour les exceptions
    non-DRF (laissées à Django / au serveur d'application).
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    code = str(getattr(exc, "default_code", "") or "error")

    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        message = str(data["detail"])
        details = {}
    elif isinstance(data, dict):
        message = "Requête invalide."
        details = data
    else:
        message = "Erreur."
        details = {"detail": data}

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
