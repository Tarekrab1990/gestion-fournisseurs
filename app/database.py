"""Accès base de données — SQLite ou PostgreSQL derrière la même interface.

Le choix se fait par la variable d'environnement DATABASE_URL :

    (absente)                          -> SQLite, fichier DATA_DIR/gestion.db
    sqlite:////chemin/absolu/base.db   -> SQLite, emplacement choisi
    postgresql://user:mdp@hote/base    -> PostgreSQL (nécessite psycopg)

Le SQL est écrit une seule fois, avec des marqueurs « ? » traduits pour
PostgreSQL au moment de l'exécution.
"""

import os
import sqlite3
import secrets
from datetime import datetime, timezone

from flask import g, current_app

from .permissions import DEFAULT_ROLES
from .security import hash_password

DEFAULT_SETTINGS = {
    "org_name": "Direction des achats",
    "seuil_devis": "350000",
    "devise": "DZD",
    "c20_validite_mois": "12",
    "c20_preavis_jours": "60",
    "alerte_debit_jours": "15",
    "validation_paiement": "1",        # 1 = un règlement doit être approuvé avant saisie
    "blocage_devis": "1",              # refuser la demande si le devis n'est pas conforme
    "blocage_dossier": "1",            # refuser la demande si le dossier fiscal est incomplet
    "blocage_facture": "1",            # refuser la demande sans facture originale remise
    "relance_c20_jours": "45",         # relancer quand le C20 expire dans moins de N jours
    "relance_intervalle_jours": "14",  # ne pas relancer le même sujet plus souvent
    "smtp_hote": "",
    "smtp_port": "587",
    "smtp_utilisateur": "",
    "smtp_tls": "1",
    "smtp_expediteur": "",
    "smtp_copie": "",
}

DEFAULT_DEPARTMENTS = [
    "Administration", "Marketing", "Foire", "Eco", "Formation",
    "Adhésion", "Projet (GTAI)", "Direction", "Communication", "Juridique",
]


# --- dialecte ----------------------------------------------------------------
def db_url():
    return os.environ.get("DATABASE_URL", "").strip()


def dialecte():
    return "postgres" if db_url().startswith(("postgres://", "postgresql://")) else "sqlite"


def _traduire(sql):
    """« ? » -> « %s » pour PostgreSQL, sans toucher aux littéraux entre quotes."""
    if dialecte() != "postgres":
        return sql
    out, dans_texte = [], False
    for ch in sql:
        if ch == "'":
            dans_texte = not dans_texte
        out.append("%s" if (ch == "?" and not dans_texte) else ch)
    return "".join(out)


# --- schéma ------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id          {PK},
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_system   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id    INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (role_id, permission)
);

CREATE TABLE IF NOT EXISTS users (
    id            {PK},
    username      TEXT NOT NULL,
    full_name     TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    is_active     INTEGER NOT NULL DEFAULT 1,
    must_change   INTEGER NOT NULL DEFAULT 0,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until  TEXT,
    last_login_at TEXT,
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users (lower(username));

CREATE TABLE IF NOT EXISTS departments (
    id        {PK},
    name      TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dept_name ON departments (lower(name));

CREATE TABLE IF NOT EXISTS suppliers (
    id            {PK},
    name          TEXT NOT NULL,
    department    TEXT DEFAULT '',
    nif           TEXT DEFAULT '',
    rc            TEXT DEFAULT '',
    rib           TEXT DEFAULT '',
    c20_provided  INTEGER NOT NULL DEFAULT 0,
    c20_date      TEXT DEFAULT '',
    contact       TEXT DEFAULT '',
    email         TEXT DEFAULT '',
    last_reminder TEXT DEFAULT '',
    note          TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    updated_by    TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers (lower(name));

CREATE TABLE IF NOT EXISTS purchase_orders (
    id                {PK},
    po_number         TEXT NOT NULL,
    po_date           TEXT NOT NULL,
    department        TEXT DEFAULT '',
    supplier_name     TEXT NOT NULL,
    description       TEXT DEFAULT '',
    amount_ttc        {REAL} NOT NULL DEFAULT 0,
    invoice_number    TEXT DEFAULT '',
    invoice_date      TEXT DEFAULT '',
    invoice_status    TEXT DEFAULT '',
    payment_mode      TEXT DEFAULT '',
    cheque_number     TEXT DEFAULT '',
    transfer_number   TEXT DEFAULT '',
    payment_date      TEXT DEFAULT '',
    debit_date        TEXT DEFAULT '',
    quote_done        INTEGER NOT NULL DEFAULT 0,
    quote_date        TEXT DEFAULT '',
    quote_signed      INTEGER NOT NULL DEFAULT 0,
    quote_approved_by TEXT DEFAULT '',
    quote_approved_at TEXT DEFAULT '',
    pay_state         TEXT NOT NULL DEFAULT 'brouillon',
    pay_requested_by  TEXT DEFAULT '',
    pay_requested_at  TEXT DEFAULT '',
    pay_decided_by    TEXT DEFAULT '',
    pay_decided_at    TEXT DEFAULT '',
    pay_decision_note TEXT DEFAULT '',
    note              TEXT DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    updated_by        TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_po_number ON purchase_orders (lower(po_number));
CREATE INDEX IF NOT EXISTS idx_po_date ON purchase_orders (po_date);
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders (supplier_name);
CREATE INDEX IF NOT EXISTS idx_po_state ON purchase_orders (pay_state);

CREATE TABLE IF NOT EXISTS attachments (
    id          {PK},
    entity      TEXT NOT NULL,
    entity_id   INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'autre',
    filename    TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime        TEXT NOT NULL DEFAULT '',
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    sha256      TEXT NOT NULL DEFAULT '',
    uploaded_by TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_entity ON attachments (entity, entity_id);

CREATE TABLE IF NOT EXISTS reminders (
    id           {PK},
    sujet        TEXT NOT NULL,
    entity       TEXT NOT NULL DEFAULT '',
    entity_id    INTEGER NOT NULL DEFAULT 0,
    destinataire TEXT NOT NULL DEFAULT '',
    statut       TEXT NOT NULL DEFAULT 'envoye',
    erreur       TEXT NOT NULL DEFAULT '',
    envoye_par   TEXT NOT NULL DEFAULT '',
    envoye_le    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rem_date ON reminders (envoye_le);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        {PK},
    ts        TEXT NOT NULL,
    username  TEXT NOT NULL DEFAULT '',
    action    TEXT NOT NULL,
    entity    TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details   TEXT NOT NULL DEFAULT '',
    ip        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
"""


def schema_sql():
    if dialecte() == "postgres":
        return _SCHEMA.format(PK="SERIAL PRIMARY KEY", REAL="DOUBLE PRECISION")
    return _SCHEMA.format(PK="INTEGER PRIMARY KEY AUTOINCREMENT", REAL="REAL")


# --- connexion ---------------------------------------------------------------
def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _Conn:
    """Enveloppe commune aux deux pilotes."""

    def __init__(self, raw, kind):
        self.raw = raw
        self.kind = kind

    def execute(self, sql, args=()):
        cur = self.raw.cursor()
        cur.execute(_traduire(sql), tuple(args))
        return cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        try:
            self.raw.rollback()
        except Exception:
            pass

    def close(self):
        self.raw.close()


def chemin_sqlite():
    url = db_url()
    if url.startswith("sqlite:///"):
        chemin = url[len("sqlite://"):]          # garde le « / » initial du chemin absolu
        return chemin if chemin.startswith("/") else chemin.lstrip("/")
    try:
        return current_app.config["DATABASE"]
    except RuntimeError:
        return os.path.join(os.environ.get("DATA_DIR", "./data"), "gestion.db")


def _connect():
    if dialecte() == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise RuntimeError(
                "DATABASE_URL pointe vers PostgreSQL mais psycopg n'est pas installé : "
                "pip install \"psycopg[binary]\""
            )
        return _Conn(psycopg.connect(db_url(), row_factory=dict_row, autocommit=False), "postgres")

    chemin = chemin_sqlite()
    dossier = os.path.dirname(os.path.abspath(chemin))
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    raw = sqlite3.connect(chemin)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode = WAL")
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA busy_timeout = 5000")
    return _Conn(raw, "sqlite")


def get_db():
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            if exc:
                conn.rollback()
        finally:
            conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    """Exécute une écriture ; renvoie l'identifiant créé pour un INSERT."""
    conn = get_db()
    retour = None
    est_insert = sql.lstrip().lower().startswith("insert")
    if est_insert and dialecte() == "postgres" and "returning" not in sql.lower():
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
    cur = conn.execute(sql, args)
    if est_insert:
        if dialecte() == "postgres":
            try:
                ligne = cur.fetchone()
                retour = (ligne or {}).get("id")
            except Exception:
                retour = None
        else:
            retour = cur.lastrowid
    cur.close()
    conn.commit()
    return retour


def insert_ignore(table, colonnes, valeurs):
    """INSERT sans échec si la ligne existe déjà, dans les deux dialectes."""
    cols = ",".join(colonnes)
    marques = ",".join("?" * len(colonnes))
    if dialecte() == "postgres":
        sql = f"INSERT INTO {table} ({cols}) VALUES ({marques}) ON CONFLICT DO NOTHING"
    else:
        sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({marques})"
    conn = get_db()
    cur = conn.execute(sql, valeurs)
    cur.close()
    conn.commit()


# --- paramètres --------------------------------------------------------------
def get_settings():
    out = dict(DEFAULT_SETTINGS)
    for r in query("SELECT key, value FROM settings"):
        out[r["key"]] = r["value"]
    return out


def get_setting(cle, defaut=None):
    r = query("SELECT value FROM settings WHERE key = ?", (cle,), one=True)
    return r["value"] if r else DEFAULT_SETTINGS.get(cle, defaut)


def set_setting(cle, valeur):
    execute("INSERT INTO settings (key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (cle, str(valeur)))


def param_bool(settings, cle):
    return str(settings.get(cle, "0")) in ("1", "true", "True", "oui")


# --- journal -----------------------------------------------------------------
def audit(action, entity="", entity_id="", details="", username=None, ip=""):
    from flask import session, request
    if username is None:
        try:
            username = session.get("username", "système")
        except RuntimeError:
            username = "système"
    if not ip:
        try:
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        except RuntimeError:
            ip = ""
    execute("INSERT INTO audit_log (ts, username, action, entity, entity_id, details, ip)"
            " VALUES (?,?,?,?,?,?,?)",
            (now(), username, action, entity, str(entity_id), details,
             (ip or "").split(",")[0].strip()))


# --- initialisation ----------------------------------------------------------
def init_db(app):
    with app.app_context():
        conn = get_db()
        for instruction in [s.strip() for s in schema_sql().split(";") if s.strip()]:
            conn.execute(instruction)
        conn.commit()
        _migrations(conn)

        for cle, valeur in DEFAULT_SETTINGS.items():
            insert_ignore("settings", ["key", "value"], (cle, valeur))
        for nom in DEFAULT_DEPARTMENTS:
            if not query("SELECT id FROM departments WHERE lower(name) = lower(?)", (nom,), one=True):
                execute("INSERT INTO departments (name) VALUES (?)", (nom,))

        for role in DEFAULT_ROLES:
            existant = query("SELECT id FROM roles WHERE code = ?", (role["code"],), one=True)
            rid = existant["id"] if existant else execute(
                "INSERT INTO roles (code, name, description, is_system) VALUES (?,?,?,?)",
                (role["code"], role["name"], role["description"], role["is_system"]))
            deja = int(query("SELECT COUNT(*) AS c FROM role_permissions WHERE role_id = ?",
                             (rid,), one=True)["c"])
            if deja == 0:
                for perm in role["permissions"]:
                    insert_ignore("role_permissions", ["role_id", "permission"], (rid, perm))

        # après une mise à jour, l'administrateur récupère les nouvelles permissions
        from .permissions import ALL_PERMISSIONS
        admin = query("SELECT id FROM roles WHERE code = 'ADMIN'", one=True)
        if admin:
            for perm in ALL_PERMISSIONS:
                insert_ignore("role_permissions", ["role_id", "permission"], (admin["id"], perm))

        nb = int(query("SELECT COUNT(*) AS c FROM users", one=True)["c"])
        if nb == 0:
            rid = query("SELECT id FROM roles WHERE code = 'ADMIN'", one=True)["id"]
            mdp = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(9)
            execute("INSERT INTO users (username, full_name, email, password_hash, role_id,"
                    " is_active, must_change, created_at) VALUES (?,?,?,?,?,1,1,?)",
                    ("admin", "Administrateur", "", hash_password(mdp), rid, now()))
            print("\n" + "=" * 68 +
                  "\n  PREMIER DEMARRAGE — compte administrateur cree"
                  "\n  Identifiant : admin"
                  f"\n  Mot de passe : {mdp}"
                  "\n  A changer des la premiere connexion."
                  "\n" + "=" * 68 + "\n", flush=True)
            try:
                dossier = os.path.dirname(app.config["DATABASE"])
                os.makedirs(dossier, exist_ok=True)
                with open(os.path.join(dossier, "MOT_DE_PASSE_INITIAL.txt"), "w", encoding="utf-8") as fh:
                    fh.write(f"admin / {mdp}\nA supprimer apres la premiere connexion.\n")
            except OSError:
                pass


def _migrations(conn):
    """Ajoute les colonnes apparues après la version 1.0, sans perte de données."""
    nouvelles = {
        "suppliers": [("email", "TEXT DEFAULT ''")],
        "purchase_orders": [
            ("pay_state", "TEXT NOT NULL DEFAULT 'brouillon'"),
            ("pay_requested_by", "TEXT DEFAULT ''"),
            ("pay_requested_at", "TEXT DEFAULT ''"),
            ("pay_decided_by", "TEXT DEFAULT ''"),
            ("pay_decided_at", "TEXT DEFAULT ''"),
            ("pay_decision_note", "TEXT DEFAULT ''"),
        ],
    }
    for table, colonnes in nouvelles.items():
        if dialecte() == "postgres":
            cur = conn.execute("SELECT column_name AS name FROM information_schema.columns"
                               " WHERE table_name = ?", (table,))
        else:
            cur = conn.execute(f"PRAGMA table_info({table})")
        presentes = {dict(r)["name"] for r in cur.fetchall()}
        cur.close()
        for nom, definition in colonnes:
            if nom not in presentes:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {definition}")
    conn.commit()
