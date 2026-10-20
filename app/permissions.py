"""Catalogue des permissions et rôles livrés d'origine.

Une permission est une chaîne `module.action`. Les rôles ne sont qu'un
ensemble de permissions : ils sont modifiables depuis l'interface
(Administration > Rôles), sauf le rôle ADMIN qui conserve toujours tout.
"""

# --- Modules de l'application ------------------------------------------------
# (code, libellé, icône, permission minimale pour voir le module)
MODULES = [
    ("tableau",       "Tableau de bord",     "◆", "tableau.view"),
    ("fournisseurs",  "Dossiers fiscaux",    "▤", "fournisseurs.view"),
    ("bons",          "Bons de commande",    "▦", "bons.view"),
    ("factures",      "Factures",            "▥", "factures.view"),
    ("paiements",     "Paiements",           "▧", "paiements.view"),
    ("devis",         "Devis comparatifs",   "▩", "devis.view"),
    ("validation",    "Validation paiements", "✓", "validation.view"),
    ("pieces",        "Pièces jointes",      "▤", "pieces.view"),
    ("relances",      "Relances",            "✉", "relances.view"),
    ("utilisateurs",  "Utilisateurs",        "◇", "admin.users"),
    ("roles",         "Rôles et permissions", "◈", "admin.roles"),
    ("referentiels",  "Départements",        "▢", "admin.departments"),
    ("journal",       "Journal d'audit",     "▭", "admin.audit"),
    ("parametres",    "Paramètres",          "▣", "admin.settings"),
]

# --- Permissions, groupées pour l'écran d'administration ---------------------
PERMISSION_GROUPS = [
    ("Tableau de bord", [
        ("tableau.view", "Consulter le tableau de bord"),
    ]),
    ("Dossiers fiscaux", [
        ("fournisseurs.view",   "Consulter les fournisseurs"),
        ("fournisseurs.edit",   "Créer et modifier un fournisseur"),
        ("fournisseurs.delete", "Supprimer un fournisseur"),
    ]),
    ("Bons de commande", [
        ("bons.view",   "Consulter les bons de commande"),
        ("bons.edit",   "Créer et modifier un bon de commande"),
        ("bons.delete", "Supprimer un bon de commande"),
    ]),
    ("Factures", [
        ("factures.view", "Consulter les factures"),
        ("factures.edit", "Saisir et modifier une facture"),
    ]),
    ("Paiements", [
        ("paiements.view", "Consulter les paiements"),
        ("paiements.edit", "Saisir un paiement et sa date de débit"),
    ]),
    ("Devis comparatifs", [
        ("devis.view",    "Consulter les devis comparatifs"),
        ("devis.edit",    "Renseigner le devis comparatif"),
        ("devis.approve", "Valider un devis comparatif"),
    ]),
    ("Circuit de validation des paiements", [
        ("validation.view",    "Consulter les demandes de règlement"),
        ("paiements.request",  "Demander la mise en paiement d'un bon"),
        ("paiements.approve",  "Approuver ou refuser une demande de règlement"),
    ]),
    ("Pièces jointes", [
        ("pieces.view",   "Consulter et télécharger les pièces jointes"),
        ("pieces.upload", "Déposer une pièce jointe"),
        ("pieces.delete", "Supprimer une pièce jointe"),
    ]),
    ("Relances", [
        ("relances.view", "Consulter l'historique des relances"),
        ("relances.send", "Envoyer une relance par courriel"),
    ]),
    ("Exports", [
        ("export.csv", "Exporter les données en CSV"),
    ]),
    ("Administration", [
        ("admin.users",       "Gérer les utilisateurs"),
        ("admin.roles",       "Gérer les rôles et leurs permissions"),
        ("admin.departments", "Gérer les départements"),
        ("admin.settings",    "Modifier les paramètres de l'application"),
        ("admin.audit",       "Consulter le journal d'audit"),
        ("admin.mail",        "Configurer la messagerie et les relances"),
    ]),
]

ALL_PERMISSIONS = [code for _, perms in PERMISSION_GROUPS for code, _ in perms]
PERMISSION_LABELS = {code: label for _, perms in PERMISSION_GROUPS for code, label in perms}

VIEW_PERMISSIONS = [p for p in ALL_PERMISSIONS if p.endswith(".view")]

# --- Rôles d'origine ---------------------------------------------------------
DEFAULT_ROLES = [
    {
        "code": "ADMIN",
        "name": "Administrateur",
        "description": "Accès complet, y compris la gestion des comptes et des paramètres.",
        "is_system": 1,
        "permissions": list(ALL_PERMISSIONS),
    },
    {
        "code": "GESTIONNAIRE",
        "name": "Gestionnaire fournisseurs",
        "description": "Tient les dossiers fiscaux, les bons de commande, les factures et les paiements.",
        "is_system": 0,
        "permissions": VIEW_PERMISSIONS + [
            "fournisseurs.edit", "bons.edit", "factures.edit",
            "paiements.edit", "devis.edit", "export.csv",
            "paiements.request", "pieces.upload", "pieces.delete", "relances.send",
        ],
    },
    {
        "code": "COMPTABLE",
        "name": "Comptabilité",
        "description": "Saisit les factures, les règlements et les dates de débit ; valide les devis comparatifs.",
        "is_system": 0,
        "permissions": VIEW_PERMISSIONS + [
            "factures.edit", "paiements.edit", "devis.approve", "export.csv",
            "paiements.approve", "pieces.upload", "relances.send",
        ],
    },
    {
        "code": "ACHETEUR",
        "name": "Acheteur",
        "description": "Crée les bons de commande et constitue les dossiers de devis comparatifs.",
        "is_system": 0,
        "permissions": [
            "tableau.view", "fournisseurs.view", "fournisseurs.edit",
            "bons.view", "bons.edit", "factures.view",
            "devis.view", "devis.edit", "export.csv",
            "validation.view", "paiements.request",
            "pieces.view", "pieces.upload", "relances.view",
        ],
    },
    {
        "code": "LECTEUR",
        "name": "Consultation",
        "description": "Lecture seule sur l'ensemble des modules métier.",
        "is_system": 0,
        "permissions": list(VIEW_PERMISSIONS),
    },
]


def modules_for(perms):
    """Modules visibles pour un ensemble de permissions."""
    return [
        {"code": c, "nom": n, "ico": i}
        for c, n, i, need in MODULES
        if need in perms
    ]
