"""Jeu d'essai repris du classeur Excel d'origine (6 fournisseurs, 12 bons)."""

from .database import execute, query, now

FOURNISSEURS = [
    # nom, département, nif, rc, rib, c20 fourni, date c20, remarque
    ("SARL Bureautique Plus", "Administration", "0987654321", "16/00-123456B",
     "007 00123 4567890123 45", 1, "2026-03-01", ""),
    ("ETS Impression Alger", "Marketing", "0912345678", "16/00-654321A",
     "005 00456 1234567890 12", 1, "2025-06-15", ""),
    ("Traiteur El Djazair", "Foire", "0955555555", "16/00-999999C",
     "011 00777 5555555555 55", 1, "2026-07-01", ""),
    ("IT Services DZ", "Administration", "0966666666", "16/00-888888D",
     "", 1, "2026-06-01", "RIB à réclamer"),
    ("Transport Sahara", "Projet (GTAI)", "", "16/00-777777E",
     "003 00111 2222222222 33", 1, "2026-05-20", "NIF à réclamer"),
    ("Agence Voyages Nord", "Eco", "0944444444", "16/00-666666F",
     "020 00888 9999999999 99", 0, "", ""),
]

BONS = [
    # date, n°, département, fournisseur, prestation, montant, n° facture, date facture,
    # état facture, mode, chèque, virement, date paiement, date débit,
    # devis fait, date devis, devis signé
    ("2026-01-12", "BC-2026-001", "Administration", "SARL Bureautique Plus", "Fournitures de bureau",
     45000, "F-101", "2026-01-15", "Facture remise", "Chèque", "CHQ-0012", "",
     "2026-01-20", "2026-01-25", 0, "", 0),
    ("2026-01-20", "BC-2026-002", "Marketing", "ETS Impression Alger", "Brochures salon",
     380000, "F-102", "2026-01-28", "Facture remise", "Virement", "", "OV-778",
     "2026-02-05", "2026-02-08", 1, "2026-01-14", 1),
    ("2026-02-03", "BC-2026-003", "Marketing", "ETS Impression Alger", "Roll-ups",
     420000, "F-115", "2026-02-10", "Facture remise", "Virement", "", "OV-801",
     "2026-02-20", "", 0, "", 0),
    ("2026-02-14", "BC-2026-004", "Foire", "Traiteur El Djazair", "Catering conférence",
     150000, "F-220", "2026-02-18", "Facture non remise", "Chèque", "CHQ-0031", "",
     "2026-02-25", "2026-03-02", 0, "", 0),
    ("2026-03-02", "BC-2026-005", "Administration", "IT Services DZ", "Maintenance serveur",
     90000, "F-330", "2026-03-05", "Facture remise", "Virement", "", "OV-850",
     "2026-03-12", "", 0, "", 0),
    ("2026-03-18", "BC-2026-006", "Eco", "Agence Voyages Nord", "Billetterie délégation",
     600000, "F-440", "2026-03-22", "Facture remise", "Virement", "", "OV-880",
     "", "", 1, "2026-03-10", 0),
    ("2026-04-05", "BC-2026-007", "Projet (GTAI)", "Transport Sahara", "Transport délégation",
     210000, "F-501", "2026-04-09", "Facture remise", "Chèque", "", "",
     "2026-04-18", "", 0, "", 0),
    ("2026-04-22", "BC-2026-008", "Formation", "Fournisseur Inconnu SARL", "Salle de formation",
     75000, "F-602", "2026-04-25", "Facture remise", "Chèque", "CHQ-0050", "",
     "", "", 0, "", 0),
    ("2026-05-06", "BC-2026-009", "Administration", "SARL Bureautique Plus", "Mobilier de bureau",
     360000, "F-707", "2026-05-10", "Facture remise", "Virement", "", "OV-910",
     "2026-05-25", "2026-05-28", 1, "2026-04-28", 1),
    ("2026-05-19", "BC-2026-010", "Foire", "Traiteur El Djazair", "Réception partenaires",
     120000, "F-808", "2026-05-24", "Facture remise", "Chèque", "CHQ-0061", "",
     "2026-06-02", "2026-06-05", 0, "", 0),
    ("2026-06-08", "BC-2026-011", "Adhésion", "SARL Bureautique Plus", "Impression cartes membres",
     30000, "F-900", "2026-06-11", "Facture non remise", "Chèque", "CHQ-0070", "",
     "", "", 0, "", 0),
    ("2026-06-25", "BC-2026-012", "Administration", "IT Services DZ", "Licences logiciels",
     500000, "F-950", "2026-07-01", "Facture remise", "Virement", "", "OV-999",
     "2026-07-10", "", 1, "2026-06-18", 0),
]


def charger_jeu_essai(username="système"):
    n = 0
    for f in FOURNISSEURS:
        if query("SELECT id FROM suppliers WHERE lower(name) = lower(?)", (f[0],), one=True):
            continue
        execute(
            "INSERT INTO suppliers (name, department, nif, rc, rib, c20_provided,"
            " c20_date, contact, email, last_reminder, note, created_at, updated_at, updated_by)"
            " VALUES (?,?,?,?,?,?,?,'','','',?,?,?,?)",
            (f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], now(), now(), username),
        )
        n += 1
    for b in BONS:
        if query("SELECT id FROM purchase_orders WHERE lower(po_number) = lower(?)",
                 (b[1],), one=True):
            continue
        execute(
            "INSERT INTO purchase_orders (po_date, po_number, department, supplier_name,"
            " description, amount_ttc, invoice_number, invoice_date, invoice_status, payment_mode,"
            " cheque_number, transfer_number, payment_date, debit_date, quote_done, quote_date,"
            " quote_signed, note, created_at, updated_at, updated_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'',?,?,?)",
            b + (now(), now(), username),
        )
        n += 1
    return n
