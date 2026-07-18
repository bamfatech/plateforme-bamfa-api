from django.conf import settings


def test_jwt_signing_key_est_configure_et_retombe_sur_secret_key():
    signing_key = settings.SIMPLE_JWT["SIGNING_KEY"]
    # Clé de signature définie et non vide
    assert signing_key
    # Par défaut (JWT_SIGNING_KEY non défini), on retombe sur la SECRET_KEY
    assert signing_key == settings.SECRET_KEY
    # Longueur suffisante pour HS256 (>= 32 octets)
    assert len(signing_key) >= 32
