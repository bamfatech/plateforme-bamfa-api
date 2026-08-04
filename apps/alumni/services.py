from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.tasks import send_templated_email_task

from .models import AlumniProfile, AlumniRegistration

INVITATION_SALT = "alumni-invitation"
INVITATION_MAX_AGE = 7 * 24 * 3600  # 7 jours
ALUMNI_GROUP = "Alumni"

# Message volontairement identique à celui d'un jeton altéré (voir
# `resolve_invitation_token` et `claim_invitation`) : un profil suspendu ou
# archivé ne doit pas être distinguable d'un jeton invalide, sans quoi
# l'erreur révélerait qu'une personne a été suspendue (§12.3 de la spec —
# non-énumération).
INVITATION_JETON_INVALIDE = "Ce lien d'invitation est invalide."


class InvitationError(Exception):
    """Base des erreurs d'invitation."""


class InvitationInvalid(InvitationError):
    pass


class InvitationExpired(InvitationError):
    pass


class InvitationAlreadyUsed(InvitationError):
    pass


def acknowledge_registration(registration):
    """Accusé de réception au demandeur."""
    send_templated_email_task.delay(
        "Votre demande d'inscription à BAMFA",
        "alumni_demande_recue",
        {"prenom": registration.first_name},
        registration.email,
    )


def build_invitation_token(profile):
    return signing.dumps({"profile_id": profile.pk}, salt=INVITATION_SALT)


def resolve_invitation_token(token):
    """Renvoie le profil visé par un jeton d'invitation.

    L'usage unique n'est pas stocké : il découle de l'invariante
    `profile.user_id is None`. Une fois le compte créé, le jeton est inerte.
    """
    try:
        data = signing.loads(token, salt=INVITATION_SALT, max_age=INVITATION_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise InvitationExpired("Ce lien d'invitation a expiré.") from exc
    except signing.BadSignature as exc:
        raise InvitationInvalid(INVITATION_JETON_INVALIDE) from exc

    profile = AlumniProfile.objects.filter(pk=data.get("profile_id")).first()
    if profile is None:
        raise InvitationInvalid(INVITATION_JETON_INVALIDE)
    if profile.user_id is not None:
        raise InvitationAlreadyUsed("Cet accès a déjà été activé.")
    if profile.status != AlumniProfile.Status.ACTIF:
        # Un profil suspendu ou archivé ne doit pas pouvoir activer un accès :
        # ni l'un ni l'autre des deux moitiés du cycle de vie (suspension,
        # invitation) ne regardait `status` avant ce correctif — voir C1 de la
        # revue finale. Même message que le jeton altéré : ne pas révéler
        # qu'une personne a été suspendue.
        raise InvitationInvalid(INVITATION_JETON_INVALIDE)
    return profile


@transaction.atomic
def claim_invitation(profile, *, password):
    """Crée le compte de connexion du profil, ou rattache un compte existant.

    Renvoie `(user, created)`. Si un compte porte déjà cette adresse, il est
    rattaché **sans** que son mot de passe soit modifié : l'invitation ne doit
    jamais servir à réécrire les identifiants d'un compte en place.

    C'est ici, et non dans `resolve_invitation_token`, que le contrôle de
    statut fait foi : le statut du profil peut changer entre la résolution du
    jeton et l'acquisition (fenêtre de course, ou suspension décidée entre
    les deux appels).
    """
    if profile.user_id is not None:
        raise InvitationAlreadyUsed("Cet accès a déjà été activé.")
    if profile.status != AlumniProfile.Status.ACTIF:
        raise InvitationInvalid(INVITATION_JETON_INVALIDE)

    User = get_user_model()
    groupe = Group.objects.get(name=ALUMNI_GROUP)
    existant = User.objects.filter(email=profile.email).first()

    if existant is not None:
        # `AlumniProfile.user` est un `OneToOneField` : un compte déjà
        # rattaché à un *autre* profil ne peut pas l'être une seconde fois
        # (l'e-mail du compte a pu diverger de celui du profil après un
        # `PATCH` administrateur — voir I6 de la revue finale). Sans ce
        # contrôle, `profile.save()` lèverait un `IntegrityError` non traduit.
        if AlumniProfile.objects.filter(user=existant).exclude(pk=profile.pk).exists():
            raise InvitationInvalid(INVITATION_JETON_INVALIDE)
        user, created = existant, False
    else:
        user = User.objects.create_user(
            email=profile.email,
            password=password,
            first_name=profile.first_name,
            last_name=profile.last_name,
        )
        created = True

    user.groups.add(groupe)
    profile.user = user
    profile.save(update_fields=["user", "updated_at"])
    return user, created


def _invitation_url(profile):
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/alumni/activation?token={build_invitation_token(profile)}"


def send_invitation(
    profile,
    *,
    template="alumni_invitation",
    subject="Activez votre accès à la plateforme BAMFA",
):
    send_templated_email_task.delay(
        subject,
        template,
        {"prenom": profile.first_name, "lien": _invitation_url(profile)},
        profile.email,
    )


# Champs recopiés de la demande vers le profil à l'approbation.
PROFILE_COPY_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "promotion",
    "country",
    "phone",
    "city",
    "university",
    "mcf_program",
    "sector",
    "current_position",
    "organization",
    "bio",
    "linkedin_url",
    "birth_date",
    "gender",
    "directory_consent",
)

REGISTRATION_ALREADY_REVIEWED_MESSAGE = "Cette demande a déjà été instruite."


class RegistrationAlreadyReviewed(Exception):
    """La demande n'est plus « en attente » au moment du verrou.

    Le contrôle de statut fait côté vue (`_en_attente_ou_400`) est une
    vérification amicale, pas la garantie : deux appels quasi simultanés
    (deux administrateurs, ou un double clic) peuvent tous deux la franchir
    avant qu'aucun n'ait committé. Cette exception porte le refus qui fait
    foi, posé sous `select_for_update()`.
    """


REGISTRATION_APPROVAL_CONFLICT_MESSAGE = (
    "Un profil existe déjà pour cette adresse e-mail. Réessayez l'approbation."
)


class RegistrationApprovalConflict(Exception):
    """Le profil n'a pas pu être créé au moment de l'approbation.

    Filet de sécurité pour une collision d'e-mail apparue entre la
    vérification (`AlumniProfile.objects.filter(email=...).first()`) et
    l'écriture elle-même — un import concurrent, par exemple. Le cas normal
    (le profil existe déjà, tout simplement) est traité juste avant, sans
    lever cette exception : voir `approve_registration`.
    """


def approve_registration(registration, *, reviewer):
    """Crée le membre depuis la demande, puis envoie le lien d'invitation.

    L'email part **après** le commit : une transaction annulée ne doit pas
    laisser filer une invitation vers un profil qui n'existe pas.

    Re-lit et verrouille la demande (`select_for_update`) avant de rejouer le
    contrôle de statut : c'est ce verrou, et non la vérification faite par la
    vue avant l'appel, qui garantit qu'une même demande ne peut être
    approuvée deux fois.

    Une demande peut porter une adresse qui a entre-temps été importée (ou
    approuvée depuis une autre demande) : la personne est alors déjà membre.
    Dans ce cas, la demande est liée au profil existant plutôt que de tenter
    d'en créer un second, qui violerait l'unicité de l'e-mail — c'est le
    comportement métier juste, pas seulement l'évitement d'une erreur.
    """
    with transaction.atomic():
        registration = AlumniRegistration.objects.select_for_update().get(
            pk=registration.pk
        )
        if registration.status != AlumniRegistration.Status.EN_ATTENTE:
            raise RegistrationAlreadyReviewed(REGISTRATION_ALREADY_REVIEWED_MESSAGE)

        profile = AlumniProfile.objects.filter(email=registration.email).first()
        if profile is None:
            try:
                with transaction.atomic():
                    profile = AlumniProfile.objects.create(
                        source=AlumniProfile.Source.INSCRIPTION,
                        **{
                            champ: getattr(registration, champ)
                            for champ in PROFILE_COPY_FIELDS
                        },
                    )
            except IntegrityError as exc:
                raise RegistrationApprovalConflict(
                    REGISTRATION_APPROVAL_CONFLICT_MESSAGE
                ) from exc

        registration.status = AlumniRegistration.Status.APPROUVEE
        registration.reviewed_by = reviewer
        registration.reviewed_at = timezone.now()
        registration.profile = profile
        registration.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "profile"]
        )

    send_invitation(
        profile,
        template="alumni_demande_approuvee",
        subject="Votre inscription à BAMFA est approuvée",
    )
    return profile


def _set_account_active(profile, actif):
    if profile.user_id is None:
        return
    if profile.user.is_active != actif:
        profile.user.is_active = actif
        profile.user.save(update_fields=["is_active"])


def _set_status(profile, status, *, account_active):
    with transaction.atomic():
        profile.status = status
        profile.save(update_fields=["status", "updated_at"])
        _set_account_active(profile, account_active)
    return profile


def suspend_profile(profile):
    """Retire le membre de l'annuaire et bloque sa connexion."""
    return _set_status(profile, AlumniProfile.Status.SUSPENDU, account_active=False)


def reactivate_profile(profile):
    return _set_status(profile, AlumniProfile.Status.ACTIF, account_active=True)


def archive_profile(profile):
    """Suppression logique : masque partout, conserve les données."""
    return _set_status(profile, AlumniProfile.Status.ARCHIVE, account_active=False)


def reject_registration(registration, *, reviewer, reason=""):
    """Rejette la demande sans rien créer. Même garantie de verrou que
    `approve_registration` : voir sa docstring."""
    with transaction.atomic():
        registration = AlumniRegistration.objects.select_for_update().get(
            pk=registration.pk
        )
        if registration.status != AlumniRegistration.Status.EN_ATTENTE:
            raise RegistrationAlreadyReviewed(REGISTRATION_ALREADY_REVIEWED_MESSAGE)

        registration.status = AlumniRegistration.Status.REJETEE
        registration.reviewed_by = reviewer
        registration.reviewed_at = timezone.now()
        registration.rejection_reason = reason or ""
        registration.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
            ]
        )

    send_templated_email_task.delay(
        "Votre demande d'inscription à BAMFA",
        "alumni_demande_rejetee",
        {"prenom": registration.first_name, "motif": registration.rejection_reason},
        registration.email,
    )
    return registration
