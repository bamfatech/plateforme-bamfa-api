from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string


def send_templated_email(*, subject, template_name, context, to, from_email=None):
    """Envoie un email transactionnel rendu depuis un template.

    Abstraction volontairement fine : aujourd'hui via le backend email Django
    (console en dev), demain via Brevo — il suffira de changer EMAIL_BACKEND,
    sans toucher aux appelants. Rend `emails/<template_name>.txt` (corps texte)
    et, si présent, `emails/<template_name>.html` (alternative HTML).
    """
    recipients = [to] if isinstance(to, str) else list(to)
    text_body = render_to_string(f"emails/{template_name}.txt", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    try:
        html_body = render_to_string(f"emails/{template_name}.html", context)
        message.attach_alternative(html_body, "text/html")
    except TemplateDoesNotExist:
        pass

    return message.send()
