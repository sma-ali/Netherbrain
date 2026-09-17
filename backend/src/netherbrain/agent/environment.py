"""L'environnement des programmes lancés par l'agent : de quoi fonctionner, sans les secrets."""

from collections.abc import Mapping

# Les seules variables transmises : de quoi trouver les programmes et afficher du texte, rien
# de plus. Une liste de ce qui est permis plutôt que de ce qui est interdit : une clé d'API
# ajoutée demain restera cachée sans y penser.
COMMAND_ENVIRONMENT = frozenset(
    {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TZ", "TMPDIR"}
)


def command_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """L'environnement d'une commande de l'agent, sans les secrets du serveur."""
    return {
        name: value
        for name, value in environ.items()
        if name in COMMAND_ENVIRONMENT or name.startswith("LC_")
    }
