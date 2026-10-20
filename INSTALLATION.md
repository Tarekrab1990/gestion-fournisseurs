# Installation sur votre serveur

Guide pas à pas. Choisissez **un seul** des trois chemins de la section 2 selon
ce dont vous disposez. Comptez vingt minutes pour une première installation.

---

## 1. Ce qu'il vous faut

| | Minimum | Confortable |
|---|---|---|
| Machine | 2 cœurs, 2 Go de RAM, 20 Go de disque | 4 cœurs, 4 Go |
| Système | Linux (Ubuntu, Debian, Rocky) ou Windows Server 2019+ | Ubuntu 22.04 ou 24.04 |
| Python | 3.10 | 3.12 |
| Réseau | les postes doivent joindre le serveur sur un port TCP | un nom DNS interne et un certificat TLS |

L'application ne sort jamais sur internet. Le seul cas où elle ouvre une
connexion vers l'extérieur est l'envoi des relances, vers **votre** serveur de
messagerie.

Décidez avant de commencer :

- **L'adresse du serveur** — son IP fixe ou, mieux, un nom DNS interne
  (`gestion.votreorganisation.local`).
- **Le compte de service** — un utilisateur système dédié, jamais root.
- **L'emplacement des données** — un dossier sauvegardé par votre système de
  sauvegarde existant. Tout y tient : base, pièces jointes, clé de session.

---

## 2. Installation

### Chemin 0 — Essai sur un Mac

Pour évaluer l'application avant de la déployer. Rien n'est installé sur le
système en dehors du dossier décompressé, et rien n'est exposé au réseau :
l'application n'écoute que sur votre propre machine.

Le plus simple : décompressez l'archive, puis **double-cliquez
`demarrer-mac.command`**. Il crée l'environnement Python au premier lancement,
démarre le serveur et ouvre le navigateur.

Si macOS refuse de l'ouvrir (« développeur non identifié »), faites un clic
droit sur le fichier → Ouvrir → Ouvrir. Ou, en une fois, dans le Terminal :

```bash
cd ~/Downloads/gestion-fournisseurs
xattr -dr com.apple.quarantine .
./demarrer-mac.command
```

En ligne de commande, si vous préférez :

```bash
cd ~/Downloads/gestion-fournisseurs
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATA_DIR=./data ADMIN_PASSWORD=Essai2026Local .venv/bin/python run.py
```

Puis ouvrez http://127.0.0.1:8000 et connectez-vous avec `admin` et le mot de
passe affiché dans le Terminal.

Chargez vos données par Administration → Paramètres → « Charger le jeu d'essai »,
ou reprenez votre classeur :

```bash
DATA_DIR=./data .venv/bin/python scripts/importer_excel.py ~/Documents/suivi.xlsx
```

À savoir sur un Mac :

- macOS est livré avec Python 3.9, ce qui suffit. Au premier appel de `python3`,
  une fenêtre peut proposer d'installer les outils de développement Apple :
  acceptez, puis relancez.
- Le port 8000 est libre par défaut ; le port 5000, lui, est occupé par AirPlay
  sur les versions récentes de macOS — n'y touchez pas.
- Pour arrêter : Ctrl-C dans le Terminal. Pour tout effacer et repartir de zéro :
  supprimez le dossier `data`.
- Pour montrer l'outil à un collègue sur le même réseau le temps d'une démo,
  lancez avec `HOST=0.0.0.0` et donnez-lui l'adresse IP de votre Mac. Réservez
  cela à une démonstration : sans HTTPS, les mots de passe circulent en clair.

Ce que vous testez ici est exactement ce qui tournera sur le serveur : même
code, même base, même jeu de permissions. Seul l'hébergement change.

### Chemin A — Linux, sans Docker (recommandé)

```bash
# 1. Dépendances système
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sqlite3 nginx

# 2. Compte de service et emplacements
sudo useradd --system --shell /usr/sbin/nologin --home /var/lib/gestion-fournisseurs gestion
sudo mkdir -p /opt/gestion-fournisseurs /var/lib/gestion-fournisseurs

# 3. Code de l'application
sudo unzip gestion-fournisseurs-onprem.zip -d /tmp
sudo cp -r /tmp/gestion-fournisseurs/* /opt/gestion-fournisseurs/
cd /opt/gestion-fournisseurs

# 4. Environnement Python
sudo python3 -m venv .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -r requirements.txt

# 5. Droits
sudo chown -R gestion:gestion /opt/gestion-fournisseurs /var/lib/gestion-fournisseurs
sudo chmod 750 /var/lib/gestion-fournisseurs
```

Créez `/etc/gestion-fournisseurs.env` :

```bash
sudo tee /etc/gestion-fournisseurs.env > /dev/null <<'FIN'
DATA_DIR=/var/lib/gestion-fournisseurs
SECRET_KEY=REMPLACEZ_MOI
ADMIN_PASSWORD=ChoisissezUnMotDePasseFort2026
COOKIE_SECURE=1
SESSION_HOURS=10
# SMTP_PASSWORD=...        (plus tard, pour les relances)
# DATABASE_URL=...         (plus tard, si vous passez à PostgreSQL)
FIN

# Générez une vraie clé et remplacez REMPLACEZ_MOI par sa valeur
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

sudo chmod 600 /etc/gestion-fournisseurs.env
sudo chown root:gestion /etc/gestion-fournisseurs.env
```

Installez le service :

```bash
sudo cp deploy/gestion-fournisseurs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gestion-fournisseurs
sudo systemctl status gestion-fournisseurs        # doit afficher "active (running)"
curl http://127.0.0.1:8000/sante                  # {"statut":"ok",...}
```

Passez à la section 3 pour le reverse proxy.

### Chemin B — Docker

```bash
unzip gestion-fournisseurs-onprem.zip && cd gestion-fournisseurs
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
nano .env                       # renseignez ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f          # le mot de passe initial s'affiche ici
```

Les données vivent dans `./data` à côté du fichier `docker-compose.yml`.
Sauvegardez ce dossier et vous sauvegardez tout.

### Chemin C — PC ou serveur Windows

> **Un guide Windows complet et autonome existe : `DEPLOIEMENT-WINDOWS.md`.**
> Il reprend tout ce qui suit en détaillant chaque étape, du téléchargement de
> Python à la liste de contrôle avant mise en production. Le résumé ci-dessous
> suffit si vous êtes à l'aise avec Windows.

> Si vous avez d'abord essayé sur un Mac, vous pouvez reprendre vos données :
> copiez le dossier `data` complet vers la machine Windows et pointez `DATA_DIR`
> dessus. La base est le même fichier des deux côtés.

**XAMPP et WAMP ne servent à rien ici.** Ils installent Apache, MySQL et PHP
pour héberger des sites PHP. Cette application est écrite en Python et embarque
déjà son serveur web ; ajouter XAMPP reviendrait à installer une pile entière
qu'il faudrait ensuite maintenir et sécuriser pour rien. La seule chose à
installer est Python.

Un PC Windows ordinaire convient parfaitement, à condition qu'il reste allumé
et qu'il ait une adresse IP fixe si d'autres postes doivent s'y connecter.

#### C1. Installer Python (une fois)

Téléchargez Python depuis <https://www.python.org/downloads/windows/>, prenez
« Windows installer (64-bit) », et **cochez « Add python.exe to PATH » sur le
premier écran de l'installateur** — c'est l'oubli le plus courant. Évitez la
version du Microsoft Store, dont les restrictions de fichiers posent problème.

Vérifiez dans une invite de commandes :

```
python --version
```

#### C2. Essai immédiat

Décompressez l'archive, par exemple dans `C:\Applications\gestion-fournisseurs`,
puis **double-cliquez `demarrer-windows.bat`**.

Il installe ce qu'il faut au premier lancement, démarre l'application et ouvre
le navigateur sur <http://127.0.0.1:8000>. Le mot de passe du compte `admin`
s'affiche dans la fenêtre noire : notez-le avant de fermer.

Windows SmartScreen peut afficher un avertissement au premier lancement :
« Informations complémentaires » puis « Exécuter quand même ».

Pour arrêter, fermez la fenêtre ou faites Ctrl-C. Rien ne tourne en arrière-plan.

#### C3. Mise en service permanente

Quand l'essai vous convient, installez le démarrage automatique. Clic droit sur
`windows\installer-service.ps1` → **Exécuter avec PowerShell**, en
administrateur. Ou, dans une console PowerShell ouverte en administrateur :

```powershell
cd C:\Applications\gestion-fournisseurs
Set-ExecutionPolicy -Scope Process Bypass -Force
.\windows\installer-service.ps1 -MotDePasseAdmin "ChoisissezUnMotDePasseFort2026"
```

Le script crée l'environnement Python, génère la clé de session, installe une
tâche planifiée qui démarre l'application **au démarrage du PC, avant même
qu'une session soit ouverte**, ouvre le port 8000 sur les profils Domaine et
Privé du pare-feu, puis affiche l'adresse à distribuer aux postes.

Options utiles :

```powershell
.\windows\installer-service.ps1 -Port 8080          # autre port
.\windows\installer-service.ps1 -LocalUniquement    # pas d'accès réseau
.\windows\installer-service.ps1 -DataDir "D:\DonneesGestion"
```

Commandes de tous les jours :

| Action | Commande |
|---|---|
| État | `schtasks /Query /TN GestionFournisseurs` |
| Arrêter | `schtasks /End /TN GestionFournisseurs` |
| Redémarrer | `schtasks /Run /TN GestionFournisseurs` |
| Journal | `notepad C:\ProgramData\GestionFournisseurs\service.log` |
| Retirer | `.\windows\desinstaller-service.ps1` |

Le compte utilisé est `SYSTEM`, ce qui évite d'avoir à créer et gérer un compte
de service. C'est un compte privilégié : n'installez l'application que sur une
machine dont vous maîtrisez l'accès physique et les comptes administrateurs.

#### C4. Accès depuis les autres postes

Donnez à la machine une **adresse IP fixe**, sans quoi l'adresse changera au
prochain redémarrage. Les collègues ouvrent alors `http://192.168.x.x:8000`.

Mieux : demandez à votre service réseau une entrée DNS interne, par exemple
`gestion.votreorganisation.local`, pour ne pas distribuer une adresse IP.

Tant que vous restez en HTTP, les mots de passe circulent en clair sur le réseau
local. C'est tolérable pour une phase d'essai entre quelques personnes, pas pour
un usage durable. Pour du HTTPS sur Windows, le plus simple est d'installer
[Caddy](https://caddyserver.com/) qui gère le certificat tout seul, ou de placer
l'application derrière votre proxy interne existant. Une fois le HTTPS en place,
passez `COOKIE_SECURE` à `1` :

```powershell
[Environment]::SetEnvironmentVariable("COOKIE_SECURE","1","Machine")
schtasks /End /TN GestionFournisseurs; schtasks /Run /TN GestionFournisseurs
```

#### C5. Sauvegardes

```powershell
.\windows\sauvegarde.ps1
```

Le script produit une archive ZIP contenant la base copiée à chaud et les pièces
jointes. Programmez-le tous les soirs dans le Planificateur de tâches : action
`powershell.exe`, arguments `-File C:\Applications\gestion-fournisseurs\windows\sauvegarde.ps1`.

Copiez ensuite ces archives ailleurs que sur le PC lui-même.

#### C6. Poste sans accès internet

Sur une machine connectée, avec la même version de Python et Windows 64 bits :

```powershell
pip download -r requirements.txt -d composants --platform win_amd64 ^
  --python-version 312 --only-binary :all:
```

Copiez le dossier `composants` à côté de l'application sur le poste cible, puis :

```powershell
python -m venv .venv
.venv\Scripts\pip install --no-index --find-links composants -r requirements.txt
```

Relancez ensuite `demarrer-windows.bat` ou le script d'installation : ils
détectent l'environnement déjà prêt et ne tentent aucun téléchargement.

### Chemin C-bis — Windows, tout à la main

Si vous préférez ne pas exécuter le script d'installation, voici ce qu'il fait,
en clair :

```powershell
cd C:\Applications\gestion-fournisseurs
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

[Environment]::SetEnvironmentVariable("DATA_DIR","C:\ProgramData\GestionFournisseurs","Machine")
[Environment]::SetEnvironmentVariable("SECRET_KEY",
    (python -c "import secrets; print(secrets.token_urlsafe(48))"),"Machine")

.venv\Scripts\waitress-serve --listen=0.0.0.0:8000 --threads=8 wsgi:application
```

Puis, pour le démarrage automatique et le pare-feu :

```powershell
schtasks /Create /TN GestionFournisseurs /SC ONSTART /RU SYSTEM /RL HIGHEST /F `
  /TR "cmd /c C:\Applications\gestion-fournisseurs\windows\service-lancer.bat"

New-NetFirewallRule -DisplayName "Gestion fournisseurs" -Direction Inbound `
  -Protocol TCP -LocalPort 8000 -Action Allow -Profile Domain,Private
```

---

## 3. Reverse proxy et HTTPS

Servir l'application directement sur le port 8000 fonctionne, mais le mot de
passe des utilisateurs circulerait en clair sur votre réseau. Mettez nginx
devant, même avec un certificat interne.

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/gestion
sudo ln -s /etc/nginx/sites-available/gestion /etc/nginx/sites-enabled/
sudo nano /etc/nginx/sites-available/gestion     # adaptez server_name et les certificats
sudo nginx -t && sudo systemctl reload nginx
```

Certificat interne auto-signé, si vous n'avez pas d'autorité interne :

```bash
sudo openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
  -keyout /etc/ssl/private/gestion.key -out /etc/ssl/certs/gestion.crt \
  -subj "/CN=gestion.votreorganisation.local"
```

Les navigateurs afficheront un avertissement tant que ce certificat n'est pas
distribué aux postes par stratégie de groupe. Un certificat émis par votre
autorité interne évite cela.

Vérifiez enfin que le port 8000 n'est **pas** joignable depuis le réseau :

```bash
sudo ufw allow 443/tcp && sudo ufw allow 80/tcp
sudo ufw deny 8000/tcp
```

---

## 4. Première connexion

1. Ouvrez `https://gestion.votreorganisation.local` depuis un poste.
2. Connectez-vous avec `admin` et le mot de passe affiché au premier démarrage
   (également écrit dans `DATA_DIR/MOT_DE_PASSE_INITIAL.txt`).
3. L'application impose immédiatement un nouveau mot de passe.
4. Supprimez le fichier :
   `sudo rm /var/lib/gestion-fournisseurs/MOT_DE_PASSE_INITIAL.txt`
5. Administration → Utilisateurs : créez un compte par personne, avec son rôle.
   Chaque création renvoie un mot de passe provisoire à transmettre.
6. Administration → Paramètres : vérifiez le seuil du devis comparatif, la
   validité du C20 et les contrôles bloquants.

Reprenez ensuite vos données :

```bash
sudo -u gestion /opt/gestion-fournisseurs/.venv/bin/python \
  /opt/gestion-fournisseurs/scripts/importer_excel.py /chemin/vers/suivi.xlsx
```

---

## 5. Messagerie et relances automatiques

1. Administration → Paramètres → Messagerie : serveur SMTP, port, adresse
   d'expédition, compte.
2. Le mot de passe SMTP ne se saisit **pas** dans l'interface. Ajoutez-le au
   fichier d'environnement, puis redémarrez :

```bash
echo 'SMTP_PASSWORD=le-mot-de-passe' | sudo tee -a /etc/gestion-fournisseurs.env
sudo systemctl restart gestion-fournisseurs
```

3. Bouton « Envoyer un message de test » pour vérifier.
4. Renseignez l'adresse de courriel de chaque fournisseur dans sa fiche.
5. Essai à blanc, puis programmation quotidienne :

```bash
sudo -u gestion /opt/gestion-fournisseurs/.venv/bin/python \
  /opt/gestion-fournisseurs/scripts/relances.py --simulation

sudo crontab -u gestion -e
# 0 8 * * * cd /opt/gestion-fournisseurs && .venv/bin/python scripts/relances.py >> /var/log/gestion-relances.log 2>&1
```

Un fournisseur n'est pas relancé deux fois sur le même sujet dans l'intervalle
réglé (14 jours par défaut).

---

## 6. Sauvegardes

Tout tient dans `DATA_DIR` : base, pièces jointes, clé de session.

```bash
sudo crontab -u gestion -e
# 0 20 * * * DATA_DIR=/var/lib/gestion-fournisseurs /opt/gestion-fournisseurs/scripts/sauvegarde.sh
```

Le script utilise `sqlite3 .backup`, qui copie une base en cours d'utilisation
sans risque d'incohérence — contrairement à un simple `cp`. Les pièces jointes
se sauvegardent avec le reste du dossier, par votre outil habituel.

Testez une restauration au moins une fois, sur une machine de test :

```bash
sudo systemctl stop gestion-fournisseurs
gunzip -c gestion-20260916-200000.db.gz | sudo -u gestion tee \
  /var/lib/gestion-fournisseurs/gestion.db > /dev/null
sudo systemctl start gestion-fournisseurs
```

---

## 7. Passer à PostgreSQL

SQLite suffit pour quelques dizaines d'utilisateurs. Passez à PostgreSQL si vous
dépassez ce cadre, si plusieurs instances doivent partager la base, ou si votre
politique interne l'impose.

```bash
sudo apt install -y postgresql
sudo -u postgres psql <<'SQL'
CREATE USER gestion WITH PASSWORD 'un-mot-de-passe-solide';
CREATE DATABASE gestion OWNER gestion ENCODING 'UTF8';
SQL

cd /opt/gestion-fournisseurs
sudo .venv/bin/pip install "psycopg[binary]"
```

Ajoutez à `/etc/gestion-fournisseurs.env` :

```
DATABASE_URL=postgresql://gestion:un-mot-de-passe-solide@127.0.0.1:5432/gestion
```

Redémarrez : le schéma est créé automatiquement au démarrage.

Pour reprendre des données déjà saisies en SQLite :

```bash
sudo systemctl stop gestion-fournisseurs
sudo -u gestion .venv/bin/python scripts/migrer_postgres.py \
  --source /var/lib/gestion-fournisseurs/gestion.db \
  --cible "postgresql://gestion:mot-de-passe@127.0.0.1:5432/gestion"
sudo systemctl start gestion-fournisseurs
```

Les pièces jointes restent des fichiers dans `DATA_DIR` : rien à migrer de ce
côté. Adaptez ensuite vos sauvegardes — `pg_dump` remplace le script SQLite.

---

## 8. Mise à jour de l'application

```bash
sudo systemctl stop gestion-fournisseurs
DATA_DIR=/var/lib/gestion-fournisseurs /opt/gestion-fournisseurs/scripts/sauvegarde.sh
sudo cp -r nouvelle-version/app nouvelle-version/scripts /opt/gestion-fournisseurs/
sudo chown -R gestion:gestion /opt/gestion-fournisseurs
sudo systemctl start gestion-fournisseurs
```

Les colonnes ajoutées par une nouvelle version sont créées automatiquement au
démarrage, sans perte de données. Ne touchez jamais à `DATA_DIR` lors d'une
mise à jour.

---

## 9. En cas de problème

| Symptôme | Cause la plus fréquente | Vérification |
|---|---|---|
| Service qui ne démarre pas | droits sur `DATA_DIR` | `sudo journalctl -u gestion-fournisseurs -n 50` |
| « 502 Bad Gateway » | l'application est arrêtée | `systemctl status gestion-fournisseurs` |
| Déconnexion à chaque rafraîchissement | `SECRET_KEY` absente et regénérée | vérifiez le fichier d'environnement |
| Impossible de se connecter en HTTPS | `COOKIE_SECURE=1` alors que le site est en HTTP | passez la variable à 0, ou activez TLS |
| Compte verrouillé | 5 échecs de connexion | attendez 15 min, ou réinitialisez depuis un compte admin |
| Relances non envoyées | `SMTP_PASSWORD` non défini | `scripts/relances.py --simulation` puis le message de test |
| Pièce jointe refusée | extension ou taille | PDF, JPEG, PNG, WEBP, TIFF, 10 Mo au maximum |
| « base is locked » (SQLite) | sauvegarde par `cp` pendant l'écriture | utilisez `scripts/sauvegarde.sh` |
| Windows : `python` inconnu | « Add python.exe to PATH » non coché | réinstallez Python en cochant la case |
| Windows : le script PowerShell ne s'exécute pas | politique d'exécution | `Set-ExecutionPolicy -Scope Process Bypass -Force` |
| Windows : rien après redémarrage | tâche non déclenchée | `schtasks /Query /TN GestionFournisseurs /V /FO LIST` |
| Windows : inaccessible depuis un autre poste | pare-feu, ou profil réseau « Public » | `Get-NetFirewallRule -DisplayName "Gestion*"` |
| Windows : l'IP du serveur a changé | adresse en DHCP | attribuez une IP fixe |

Journaux utiles :

```bash
sudo journalctl -u gestion-fournisseurs -f     # application
sudo tail -f /var/log/nginx/error.log          # proxy
```

Le journal d'audit dans l'application, lui, répond à la question « qui a fait
quoi » : connexions, créations, modifications, approbations, relances.
