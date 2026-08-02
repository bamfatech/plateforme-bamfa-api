from apps.common.emails import send_templated_email


def test_envoi_email_template(mailoutbox):
    envoyes = send_templated_email(
        subject="Bienvenue",
        template_name="exemple",
        context={"nom": "Awa"},
        to="awa@example.org",
    )
    assert envoyes == 1
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.subject == "Bienvenue"
    assert message.to == ["awa@example.org"]
    assert "Awa" in message.body


def test_destinataire_unique_accepte_une_chaine(mailoutbox):
    send_templated_email(
        subject="Test", template_name="exemple", context={"nom": "X"}, to="x@example.org"
    )
    assert mailoutbox[0].to == ["x@example.org"]
