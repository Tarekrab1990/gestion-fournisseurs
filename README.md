# Gestion des fournisseurs et des paiements

Application interne pour le suivi des dossiers fiscaux fournisseurs, des bons de
commande, des factures et des règlements. Elle s'installe sur votre propre
serveur : aucune donnée ne sort de votre réseau.

**Pour installer sur Windows : lisez `DEPLOIEMENT-WINDOWS.md`.**
**Pour Linux, Docker ou macOS : lisez `INSTALLATION.md`.** Ce fichier-ci décrit ce que fait
l'application ; l'autre explique pas à pas comment la mettre en service.

- **Backend** — Python 3.10+ et Flask, base SQLite ou PostgreSQL au choix.
- **Frontend** — HTML, CSS et JavaScript natifs. Aucune dépendance téléchargée
  à l'exécution : l'application fonctionne sur un réseau sans accès internet.
- **Empreinte** — un processus, un fichier de base. Une machine à 2 cœurs et
  2 Go de RAM suffit largement pour quelques dizaines d'utilisateurs.

---

## 1. Essai en cinq minutes

Pour une vraie mise en service, allez directement à `INSTALLATION.md`.

```bash
cd gestion-fournisseurs
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Ouvrez http://127.0.0.1:8000.

Au tout premier démarrage, un compte `admin` est créé et **son mot de passe
s'affiche dans la console**. Il est aussi écrit dans
`data/MOT_DE_PASSE_INITIAL.txt` — supprimez ce fichier après la première
connexion. Pour choisir le mot de passe vous-même, définissez `ADMIN_PASSWORD`
avant le premier lancement.

## 2. Installation en production

### Avec Docker

```bash
cp .env.example .env               # renseignez SECRET_KEY et ADMIN_PASSWORD
docker compose up -d --build
```

La base vit dans `./data`, monté en volume : sauvegardez ce dossier et vous
sauvegardez tout. Le port n'est publié que sur `127.0.0.1` ; placez un reverse
proxy TLS devant (exemple fourni dans `deploy/nginx.conf`).

### Sans Docker, avec systemd

```bash
sudo useradd --system --home /var/lib/gestion-fournisseurs gestion
sudo mkdir -p /opt/gestion-fournisseurs /var/lib/gestion-fournisseurs
sudo cp -r . /opt/gestion-fournisseurs
cd /opt/gestion-fournisseurs
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo chown -R gestion /opt/gestion-fournisseurs /var/lib/gestion-fournisseurs

sudo cp deploy/gestion-fournisseurs.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now gestion-fournisseurs
```

Variables d'environnement dans `/etc/gestion-fournisseurs.env` (voir
`.env.example`). Sous Windows Server, remplacez gunicorn par waitress :

```
waitress-serve --listen=127.0.0.1:8000 wsgi:application
```

### Points à régler avant la mise en service

| À faire | Pourquoi |
|---|---|
| Servir en HTTPS et mettre `COOKIE_SECURE=1` | le cookie de session ne doit pas circuler en clair |
| Fixer `SECRET_KEY` | sans elle, un fichier est généré ; en cluster chaque instance en aurait une différente |
| Programmer `scripts/sauvegarde.sh` | une base SQLite se sauvegarde à chaud, pas en copiant le fichier |
| Changer le mot de passe `admin` | il est provisoire et l'application l'exige à la première connexion |

## 3. Reprise de vos données Excel

```bash
python scripts/importer_excel.py /chemin/vers/suivi.xlsx
python scripts/importer_excel.py /chemin/vers/suivi.xlsx --remplacer   # mise à jour
```

Le script lit les feuilles « Fournisseurs » et « Paiements » du classeur
d'origine. Les colonnes calculées du classeur (expiration du C20, alertes,
statuts, contrôles de devis) sont **ignorées** : l'application les recalcule à
partir des données sources, ce qui évite de réimporter les `#REF!` du fichier.

Un jeu d'essai de 6 fournisseurs et 12 bons est également disponible depuis
Administration → Paramètres, tant que la base ne contient aucun fournisseur.

## 4. Modules

| Module | Contenu |
|---|---|
| Tableau de bord | Ce qui bloque un paiement, classé par urgence, et récapitulatif mensuel |
| Dossiers fiscaux | NIF, RC/agrément, RIB, C20 ; expiration et alerte calculées |
| Bons de commande | Une ligne par BC, rattachée au mois de sa création |
| Factures | Réception des originaux, délai facture → paiement |
| Paiements | Chèque ou virement, date de paiement, date de débit |
| Devis comparatifs | Bons au-dessus du seuil, avec réalisation, date, signature et validation |
| Validation paiements | Demandes de règlement, approbation ou refus motivé |
| Pièces jointes | C20, factures et devis numérisés, rattachés aux fiches |
| Relances | Courriels aux fournisseurs, à la demande ou automatiques |
| Utilisateurs | Comptes, rôle, activation, réinitialisation de mot de passe |
| Rôles et permissions | Matrice modifiable, permission par permission |
| Départements | Référentiel des départements émetteurs |
| Journal d'audit | Connexions et écritures, horodatées et nominatives |
| Paramètres | Seuil du devis, validité du C20, délais d'alerte, devise |

## 5. Règles de gestion

Toutes sont appliquées côté serveur ; l'interface ne fait que les afficher.

- **C20** — expire `c20_validite_mois` mois après sa date (12 par défaut).
  L'alerte passe à « expire bientôt » `c20_preavis_jours` jours avant l'échéance.
- **Statut du dossier** — *Complet* quand NIF, RC/agrément, RIB et un C20 en
  cours de validité sont tous présents ; *Incomplet* sinon, avec la liste des
  pièces manquantes.
- **Devis comparatif** — obligatoire dès que le montant TTC **atteint** le seuil
  (350 000 par défaut, paramétrable). Le dossier doit être réalisé, daté et
  signé, puis validé par un profil habilité. Toute modification ultérieure du
  devis annule la validation.
- **Statut de paiement** — déduit des dates, jamais saisi : *À payer* sans date
  de paiement, *Payé – en attente de débit* avec une date de paiement seule,
  *Payé et débité* quand la date de débit est renseignée.
- **Rattachement mensuel** — un bon appartient au mois de sa date de création et
  n'en change jamais.
- **Circuit de validation** — quand il est actif, aucune date de paiement ne
  peut être saisie tant que le bon n'a pas été approuvé. Une demande est refusée
  d'office si le devis comparatif n'est pas conforme, si le dossier fiscal est
  incomplet ou si la facture originale n'a pas été remise ; chacun de ces trois
  contrôles se désactive séparément dans les paramètres. Un refus doit être
  motivé, et le motif reste attaché au bon.
- **Relances** — un fournisseur n'est pas relancé deux fois sur le même sujet à
  l'intérieur de l'intervalle réglé (14 jours par défaut).

Modifier un paramètre recalcule immédiatement les contrôles de toutes les
lignes : abaisser le seuil fait apparaître les bons devenus concernés.

## 6. Rôles livrés

| Rôle | Portée |
|---|---|
| Administrateur | Tout, y compris comptes, rôles et paramètres |
| Gestionnaire fournisseurs | Dossiers, bons, factures, paiements, devis |
| Comptabilité | Factures, paiements, approbation des règlements et des devis |
| Acheteur | Fournisseurs, bons, constitution des devis, demande de règlement |
| Consultation | Lecture seule |

Ces rôles sont un point de départ : la matrice se modifie dans
Administration → Rôles. Le rôle Administrateur conserve toujours l'ensemble des
permissions, et l'application refuse de supprimer ou désactiver le dernier
administrateur actif.

Les permissions sont vérifiées **champ par champ** sur un bon de commande. Un
acheteur qui renseigne une date de paiement est refusé ; un comptable qui
modifie le montant l'est aussi. Le message indique précisément ce qui manque.

La séparation des tâches est volontaire : *demander* un règlement
(`paiements.request`) et l'*approuver* (`paiements.approve`) sont deux
permissions distinctes, qu'aucun rôle livré ne détient ensemble. Il en va de
même pour la saisie et la validation d'un devis comparatif.

## 7. Pièces jointes

Chaque fiche fournisseur et chaque bon de commande accepte des documents
numérisés : C20, RC, RIB, facture originale, devis comparatif, justificatif de
règlement. Formats acceptés : PDF, JPEG, PNG, WEBP, TIFF, 10 Mo au maximum.

Les fichiers sont écrits dans `DATA_DIR/pieces-jointes`, jamais en base : leur
nom sur disque vient de l'empreinte SHA-256 du contenu, deux dépôts identiques
ne consomment donc qu'un fichier. Le type déclaré est confronté au contenu réel,
et la permission exigée dépend de la nature du document — joindre une facture
demande `factures.edit`, un devis comparatif `devis.edit`.

## 8. Relances par courriel

Deux relances sont gérées : le C20 (absent, expiré ou proche de l'échéance) et
la facture originale non remise. Elles partent à la demande depuis l'interface,
ou automatiquement via `scripts/relances.py` programmé une fois par jour.

Les réglages SMTP se font dans l'interface, sauf le mot de passe, lu dans la
variable d'environnement `SMTP_PASSWORD` pour ne jamais se trouver en base.
Essayez d'abord `python scripts/relances.py --simulation`, qui affiche ce qui
serait envoyé sans rien expédier.

Quand une demande de règlement est déposée, les comptes disposant de
`paiements.approve` et d'une adresse de courriel en sont avertis.

## 9. Sécurité

- Mots de passe stockés en PBKDF2-SHA256, 260 000 itérations, sel par compte.
- Session par cookie signé, `HttpOnly`, `SameSite=Lax`, durée réglable.
- Jeton anti-CSRF exigé sur toute écriture.
- Verrouillage du compte 15 minutes après 5 échecs de connexion.
- En-têtes `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`.
- Journal d'audit : connexions réussies et refusées, créations, modifications
  et suppressions, avec l'utilisateur, l'horodatage et l'adresse IP.

L'application n'envoie pas de courriels et n'appelle aucun service tiers.

## 10. Sauvegarde et restauration

```bash
DATA_DIR=/var/lib/gestion-fournisseurs ./scripts/sauvegarde.sh
```

Restauration : arrêtez le service, décompressez l'archive par-dessus
`gestion.db`, redémarrez.

```bash
sudo systemctl stop gestion-fournisseurs
gunzip -c sauvegardes/gestion-20260916-200000.db.gz > /var/lib/gestion-fournisseurs/gestion.db
sudo systemctl start gestion-fournisseurs
```

Conservez `secret.key` avec la base : sans elle, les sessions ouvertes sont
invalidées (sans perte de données).

## 11. Structure du projet

```
app/
  __init__.py      fabrique Flask, en-têtes de sécurité
  auth.py          connexion, déconnexion, mot de passe
  api.py           fournisseurs, bons, factures, paiements, devis, exports
  admin.py         comptes, rôles, départements, paramètres, journal
  attachments.py   dépôt, téléchargement et suppression des pièces jointes
  mailer.py        envoi SMTP et modèles de relance
  rules.py         règles de gestion — le seul endroit où elles vivent
  permissions.py   catalogue des permissions et rôles d'origine
  database.py      schéma et initialisation, SQLite ou PostgreSQL
  security.py      mots de passe, CSRF, décorateurs de permission
  demo.py          jeu d'essai
  static/          app.js, style.css
  templates/       index.html
demarrer-mac.command    lanceur double-cliquable, macOS
demarrer-windows.bat    lanceur double-cliquable, Windows
windows/
  installer-service.ps1   demarrage automatique, pare-feu, cle de session
  desinstaller-service.ps1
  service-lancer.bat      lance par la tache planifiee
  sauvegarde.ps1          sauvegarde a chaud, Windows
scripts/
  importer_excel.py   reprise du classeur
  relances.py         relances quotidiennes (cron)
  migrer_postgres.py  bascule SQLite -> PostgreSQL
  sauvegarde.sh       sauvegarde à chaud
deploy/
  gestion-fournisseurs.service, nginx.conf
```

Pour ajouter un contrôle métier, modifiez `app/rules.py` : le tableau de bord,
les listes et les exports s'alignent automatiquement. Pour ajouter une
permission, déclarez-la dans `app/permissions.py`, puis affectez-la aux rôles
depuis l'interface.

## 12. Limites connues

- SQLite convient à un usage interne courant. Au-delà, ou si plusieurs instances
  doivent partager la base, basculez sur PostgreSQL (`DATABASE_URL` et
  `scripts/migrer_postgres.py`). Le chemin PostgreSQL est implémenté et le
  dialecte testé, mais il n'a pas été exécuté contre un serveur réel : validez-le
  sur un jeu de données de test avant de basculer la production.
- Les pièces jointes ne sont pas analysées par un antivirus. Si votre politique
  l'exige, faites pointer votre antivirus sur `DATA_DIR/pieces-jointes`.
- Pas de signature électronique des devis : l'application enregistre qu'un devis
  est signé, elle ne signe rien.
- Pas de rapprochement bancaire automatique : les dates de débit se saisissent.
