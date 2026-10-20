# Déploiement sur Windows — guide complet

Ce document se suffit à lui-même. Suivez-le du début à la fin : à la dernière
page, l'application tournera sur votre PC Windows, démarrera toute seule après
un redémarrage, et vos collègues y accéderont depuis leur poste.

Comptez trente minutes la première fois.

**Sommaire**

1. [Avant de commencer](#1-avant-de-commencer)
2. [Pourquoi pas XAMPP](#2-pourquoi-pas-xampp)
3. [Étape 1 — Installer Python](#3-étape-1--installer-python)
4. [Étape 2 — Déposer l'application](#4-étape-2--déposer-lapplication)
5. [Étape 3 — Premier essai](#5-étape-3--premier-essai)
6. [Étape 4 — Mise en service permanente](#6-étape-4--mise-en-service-permanente)
7. [Étape 5 — Accès depuis les autres postes](#7-étape-5--accès-depuis-les-autres-postes)
8. [Étape 6 — Comptes et paramètres](#8-étape-6--comptes-et-paramètres)
9. [Étape 7 — Reprise de vos données Excel](#9-étape-7--reprise-de-vos-données-excel)
10. [Étape 8 — Sauvegardes](#10-étape-8--sauvegardes)
11. [Étape 9 — Messagerie et relances](#11-étape-9--messagerie-et-relances)
12. [Étape 10 — Passer en HTTPS](#12-étape-10--passer-en-https)
13. [Exploitation au quotidien](#13-exploitation-au-quotidien)
14. [Mise à jour de l'application](#14-mise-à-jour-de-lapplication)
15. [Dépannage](#15-dépannage)
16. [Poste sans accès internet](#16-poste-sans-accès-internet)
17. [Tout désinstaller](#17-tout-désinstaller)
18. [Aide-mémoire](#18-aide-mémoire)

---

## 1. Avant de commencer

### La machine

| | Minimum | Confortable |
|---|---|---|
| Système | Windows 10, Windows 11, ou Windows Server 2016+ | Windows Server 2022 |
| Processeur | 2 cœurs | 4 cœurs |
| Mémoire | 4 Go | 8 Go |
| Disque libre | 5 Go | 20 Go et plus, selon les pièces jointes |

Un PC de bureau ordinaire convient. L'application consomme très peu : c'est un
seul processus Python et un fichier de base de données.

### Les trois conditions

**La machine doit rester allumée.** Si c'est le PC d'un collègue qui l'éteint
le soir, personne d'autre ne pourra travailler le lendemain matin avant son
arrivée. Choisissez une machine qui reste sous tension, et désactivez la mise
en veille : Paramètres → Système → Alimentation → Veille → « Jamais ».

**La machine doit avoir une adresse IP fixe** si d'autres postes s'y connectent.
Sinon l'adresse changera au prochain redémarrage et les raccourcis de chacun
cesseront de fonctionner. Demandez à votre service informatique une réservation
DHCP ou une IP statique.

**Vous devez être administrateur** de cette machine pour l'étape 4.

### Ce qu'il faut décider maintenant

| Décision | Valeur par défaut | Notez la vôtre |
|---|---|---|
| Emplacement de l'application | `C:\Applications\gestion-fournisseurs` | |
| Emplacement des données | `C:\ProgramData\GestionFournisseurs` | |
| Port réseau | 8000 | |
| Mot de passe du compte `admin` | (généré) | |

L'emplacement des données est le seul dossier à sauvegarder : il contient la
base, les pièces jointes et la clé de session. Si vous avez un second disque,
mettez-le dessus (`D:\DonneesGestion`).

### Ce que l'application fait sur le réseau

Elle n'appelle jamais internet. La seule connexion sortante possible est vers
**votre** serveur de messagerie, et uniquement si vous activez les relances à
l'étape 9. Le seul téléchargement a lieu une fois, à l'installation, pour
récupérer les composants Python depuis pypi.org — voyez la section 16 si le
poste n'a pas d'accès internet.

---

## 2. Pourquoi pas XAMPP

XAMPP, WAMP et Laragon installent Apache, MySQL et PHP pour héberger des sites
écrits en PHP. Cette application est écrite en **Python** et embarque déjà son
propre serveur web. Les faire cohabiter reviendrait à installer et maintenir une
pile complète qui ne servirait à rien, tout en élargissant la surface d'attaque
de la machine.

La seule chose à installer est Python. Ce que vous connaissez d'un déploiement
XAMPP se retrouve ici sous une autre forme :

| Avec XAMPP | Ici |
|---|---|
| Apache | serveur intégré (waitress), démarré par une tâche planifiée |
| MySQL | SQLite, un simple fichier dans le dossier de données |
| phpMyAdmin | l'application elle-même ; ou l'outil DB Browser for SQLite si besoin |
| `htdocs` | `C:\Applications\gestion-fournisseurs` |
| Panneau de contrôle XAMPP | commandes `schtasks` de la section 13 |

---

## 3. Étape 1 — Installer Python

À faire une seule fois par machine.

1. Ouvrez <https://www.python.org/downloads/windows/>
2. Sous la dernière version 3.12 ou 3.13, prenez **« Windows installer (64-bit) »**.
3. Lancez le fichier téléchargé.
4. **Sur le premier écran, cochez « Add python.exe to PATH »**, en bas.
   C'est l'erreur la plus fréquente : sans cette case, rien ne fonctionnera
   ensuite et il faudra tout réinstaller.
5. Cliquez « Install Now » et laissez faire.

> **N'utilisez pas la version du Microsoft Store.** Elle s'exécute dans un bac à
> sable qui pose problème avec les fichiers et les tâches planifiées.

### Vérification

Ouvrez une invite de commandes : touche Windows, tapez `cmd`, Entrée. Puis :

```
python --version
```

Vous devez voir quelque chose comme `Python 3.12.7`. Si vous obtenez « n'est pas
reconnu en tant que commande », la case PATH n'a pas été cochée : relancez
l'installateur, choisissez « Modify », puis « Add Python to environment
variables ».

---

## 4. Étape 2 — Déposer l'application

1. Créez le dossier `C:\Applications`.
2. Copiez-y `gestion-fournisseurs-onprem.zip`.
3. Clic droit sur le fichier → **Extraire tout** → extraire dans `C:\Applications`.

Vous devez obtenir cette arborescence :

```
C:\Applications\gestion-fournisseurs\
    app\
    scripts\
    windows\
    data\
    demarrer-windows.bat
    run.py
    requirements.txt
    README.md
    INSTALLATION.md
    DEPLOIEMENT-WINDOWS.md   (ce document)
```

> Si vous voyez `gestion-fournisseurs\gestion-fournisseurs\...`, l'extraction a
> créé un niveau en trop. Remontez le contenu d'un cran.

Ne mettez pas l'application dans `C:\Program Files` : les droits d'écriture y
sont restreints et compliquent inutilement les mises à jour.

---

## 5. Étape 3 — Premier essai

Cet essai ne touche à rien sur le système : tout reste dans le dossier extrait,
et l'application n'écoute que sur la machine elle-même.

**Double-cliquez `demarrer-windows.bat`.**

Il se passe ceci :

1. Une fenêtre noire s'ouvre.
2. Au premier lancement, elle affiche « Première installation, patientez environ
   une minute ». Le script crée l'environnement Python et télécharge les
   composants. C'est le seul moment où internet est nécessaire.
3. L'application démarre et le navigateur s'ouvre sur <http://127.0.0.1:8000>.

> **Windows SmartScreen** peut afficher « Windows a protégé votre ordinateur ».
> Cliquez « Informations complémentaires » puis « Exécuter quand même ». C'est
> normal pour un script non signé.
>
> **Le pare-feu** peut demander une autorisation. Pour cet essai local, vous
> pouvez refuser : l'application n'a pas besoin du réseau à ce stade.

### Première connexion

Le **mot de passe du compte `admin`** s'affiche dans la fenêtre noire, dans un
encadré. Notez-le. Il est aussi écrit dans
`C:\Applications\gestion-fournisseurs\data\MOT_DE_PASSE_INITIAL.txt`.

Connectez-vous avec l'identifiant `admin` et ce mot de passe. L'application
exige immédiatement d'en choisir un nouveau.

### Explorer

Allez dans **Administration → Paramètres** et cliquez « Charger le jeu d'essai » :
six fournisseurs et douze bons de commande apparaissent, de quoi parcourir tous
les modules sans rien saisir.

### Arrêter

Fermez la fenêtre noire, ou faites Ctrl-C dedans. Rien ne continue en
arrière-plan.

### Repartir de zéro

Supprimez le dossier `data`, puis relancez. Tout est effacé : base, comptes,
pièces jointes.

> **Si l'essai vous convient, passez à l'étape 4.** Les données saisies pendant
> l'essai ne seront pas reprises automatiquement : l'installation permanente
> utilise un autre dossier. Voyez la section 15 si vous voulez les conserver.

---

## 6. Étape 4 — Mise en service permanente

Cette étape installe l'application pour de bon : elle démarrera automatiquement
au démarrage du PC, **avant même qu'un utilisateur ouvre sa session**, et
restera disponible tant que la machine est allumée.

### Lancer l'installation

1. Ouvrez le dossier `windows`.
2. Clic droit sur `installer-service.ps1` → **Exécuter avec PowerShell**.
3. Si Windows demande une élévation, acceptez.

Si le clic droit ne propose pas cette option, ou si le script se ferme
aussitôt : touche Windows, tapez `powershell`, **clic droit → Exécuter en tant
qu'administrateur**, puis :

```powershell
cd C:\Applications\gestion-fournisseurs
Set-ExecutionPolicy -Scope Process Bypass -Force
.\windows\installer-service.ps1 -MotDePasseAdmin "ChoisissezUnMotDePasseFort2026"
```

`Set-ExecutionPolicy -Scope Process` ne s'applique qu'à cette fenêtre et
n'affaiblit pas durablement la sécurité du poste.

### Options

```powershell
# Autre port, si 8000 est déjà pris
.\windows\installer-service.ps1 -Port 8080

# Données sur un autre disque
.\windows\installer-service.ps1 -DataDir "D:\DonneesGestion"

# Aucun accès depuis le réseau (usage sur cette machine seulement)
.\windows\installer-service.ps1 -LocalUniquement

# Tout combiné
.\windows\installer-service.ps1 -Port 8080 -DataDir "D:\DonneesGestion" `
    -MotDePasseAdmin "UnMotDePasseFort2026"
```

### Ce que le script fait, en clair

| Action | Détail |
|---|---|
| Vérifie Python | version 3.9 minimum |
| Crée l'environnement | dossier `.venv` dans l'application |
| Installe les composants | Flask, waitress, openpyxl |
| Génère la clé de session | aléatoire, stockée en variable machine `SECRET_KEY` |
| Crée le dossier de données | `C:\ProgramData\GestionFournisseurs` par défaut |
| Déclare la tâche planifiée | `GestionFournisseurs`, déclenchée au démarrage, compte `SYSTEM` |
| Ouvre le pare-feu | port 8000, profils **Domaine et Privé** seulement |
| Démarre l'application | et vérifie qu'elle répond |

À la fin, il affiche l'adresse locale, l'adresse réseau, et les identifiants de
première connexion.

> **Sur le compte `SYSTEM`** : c'est ce qui permet à l'application de démarrer
> sans session ouverte, sans avoir à créer et gérer un compte de service avec
> son mot de passe. C'est un compte privilégié. N'installez l'application que
> sur une machine dont vous maîtrisez l'accès physique et la liste des
> administrateurs.

### Vérifier que c'est en place

```powershell
schtasks /Query /TN GestionFournisseurs
```

Doit afficher l'état `Running` (ou `En cours d'exécution`).

```powershell
Invoke-RestMethod http://127.0.0.1:8000/sante
```

Doit répondre `statut : ok` et le numéro de version.

**Test décisif** : redémarrez le PC, attendez l'écran de connexion Windows
**sans ouvrir de session**, et depuis un autre poste ouvrez
`http://adresse-du-serveur:8000`. La page de connexion doit s'afficher. Si oui,
l'installation est réussie.

---

## 7. Étape 5 — Accès depuis les autres postes

### Trouver l'adresse du serveur

Sur la machine serveur :

```powershell
ipconfig
```

Relevez l'« Adresse IPv4 » de la carte réseau active, par exemple
`192.168.1.42`. Les collègues ouvriront `http://192.168.1.42:8000`.

### Fixer l'adresse

Si cette adresse vient du DHCP, elle changera. Demandez à votre service réseau
une **réservation DHCP** sur l'adresse MAC de la machine — c'est plus propre
qu'une IP statique saisie à la main, qui risque d'entrer en conflit.

### Mieux : un nom plutôt qu'une adresse

Demandez une entrée DNS interne, par exemple
`gestion.votreorganisation.local` pointant vers l'IP. Les collègues retiennent
un nom, et le jour où la machine change, vous modifiez une seule ligne au lieu
de prévenir tout le monde.

### Vérifier depuis un autre poste

```powershell
Test-NetConnection -ComputerName 192.168.1.42 -Port 8000
```

`TcpTestSucceeded : True` signifie que le chemin réseau est bon. Si c'est
`False`, voyez le dépannage en section 15.

### Distribuer l'accès

Envoyez simplement le lien. Rien à installer sur les postes clients : un
navigateur suffit, y compris sur téléphone et tablette du même réseau.

> **Attention** : tant que vous êtes en HTTP, les mots de passe circulent en
> clair sur le réseau local. Acceptable pour quelques semaines d'essai entre
> trois personnes, pas au-delà. Voyez l'étape 10.

---

## 8. Étape 6 — Comptes et paramètres

Connectez-vous en `admin` et faites le tour dans cet ordre.

### Supprimer le mot de passe initial

Une fois connecté et le mot de passe changé, supprimez le fichier :

```powershell
Remove-Item C:\ProgramData\GestionFournisseurs\MOT_DE_PASSE_INITIAL.txt
```

### Créer les comptes

**Administration → Utilisateurs → Créer un compte.** Un compte par personne,
jamais un compte partagé : le journal d'audit ne vaut que si chaque écriture
porte un nom.

Chaque création renvoie un mot de passe provisoire à transmettre. L'utilisateur
devra le changer à sa première connexion.

Les cinq rôles livrés :

| Rôle | Pour qui | Ce qu'il peut faire |
|---|---|---|
| Administrateur | vous | tout, y compris comptes et paramètres |
| Gestionnaire fournisseurs | le ou la responsable du suivi | dossiers, bons, factures, paiements, devis |
| Comptabilité | la comptabilité | factures, règlements, approbation des devis et des paiements |
| Acheteur | les services qui commandent | fournisseurs, bons, devis, demande de règlement |
| Consultation | direction, audit | lecture seule |

**Administration → Rôles** permet de modifier la matrice permission par
permission si aucun de ces rôles ne correspond exactement.

> Gardez la séparation entre *demander* un règlement et l'*approuver* : aucun
> rôle livré ne détient les deux, et c'est délibéré.

### Régler les paramètres

**Administration → Paramètres.** Vérifiez au minimum :

- **Seuil du devis comparatif** — 350 000 par défaut, atteint inclus.
- **Validité du C20** — 12 mois.
- **Préavis d'expiration** — 60 jours.
- **Circuit de validation des règlements** — actif par défaut. S'il l'est,
  aucune date de paiement ne peut être saisie avant approbation.
- **Les trois contrôles bloquants** — devis non conforme, dossier fiscal
  incomplet, facture originale non remise. Désactivez individuellement ceux qui
  ne correspondent pas à vos pratiques.

### Les départements

**Administration → Départements.** Adaptez la liste à votre organigramme.
Désactivez plutôt que de supprimer un département auquel des bons sont
rattachés.

---

## 9. Étape 7 — Reprise de vos données Excel

Ouvrez une invite de commandes **en administrateur** :

```
cd C:\Applications\gestion-fournisseurs
set DATA_DIR=C:\ProgramData\GestionFournisseurs
.venv\Scripts\python.exe scripts\importer_excel.py "C:\Users\vous\Documents\suivi.xlsx"
```

Le script lit les feuilles « Fournisseurs » et « Paiements ». Les colonnes
calculées du classeur — expiration du C20, alertes, statuts, contrôles — sont
**ignorées volontairement** : l'application les recalcule à partir des données
sources, ce qui évite de réimporter les `#REF!` du fichier.

Pour mettre à jour des lignes déjà importées :

```
.venv\Scripts\python.exe scripts\importer_excel.py "C:\...\suivi.xlsx" --remplacer
```

**Après l'import**, passez dans le module « Devis comparatifs » : les dates de
devis et les signatures ne figurent pas toutes dans le classeur d'origine et
demandent une vérification.

---

## 10. Étape 8 — Sauvegardes

### Essai manuel

```powershell
cd C:\Applications\gestion-fournisseurs
.\windows\sauvegarde.ps1
```

Une archive ZIP est créée dans `C:\ProgramData\GestionFournisseurs\sauvegardes`,
contenant la base copiée à chaud et les pièces jointes.

> La base est copiée par la commande `.backup` de SQLite, qui produit un
> fichier cohérent même si quelqu'un travaille pendant ce temps. **Ne copiez
> jamais `gestion.db` avec l'Explorateur pendant que l'application tourne** :
> vous obtiendriez un fichier corrompu.

### Automatiser

Planificateur de tâches → Créer une tâche :

| Onglet | Réglage |
|---|---|
| Général | Nom : `Sauvegarde gestion fournisseurs` ; « Exécuter même si l'utilisateur n'est pas connecté » ; « Exécuter avec les autorisations maximales » |
| Déclencheurs | Quotidien, 20:00 |
| Actions | Programme : `powershell.exe`<br>Arguments : `-ExecutionPolicy Bypass -File "C:\Applications\gestion-fournisseurs\windows\sauvegarde.ps1"` |
| Conditions | décochez « Démarrer seulement si l'ordinateur est sur secteur » |

### Sortir les sauvegardes de la machine

Une sauvegarde qui reste sur le PC ne protège de rien en cas de panne disque ou
de rançongiciel. Copiez le dossier `sauvegardes` sur un partage réseau, un NAS
ou un disque externe — par votre outil de sauvegarde habituel, ou par une tâche
planifiée avec `robocopy`.

### Restaurer

```powershell
schtasks /End /TN GestionFournisseurs
Expand-Archive "C:\...\gestion-20260916-200000.zip" -DestinationPath "$env:TEMP\restauration"
Copy-Item "$env:TEMP\restauration\gestion.db" "C:\ProgramData\GestionFournisseurs\gestion.db" -Force
Copy-Item "$env:TEMP\restauration\pieces-jointes" "C:\ProgramData\GestionFournisseurs\" -Recurse -Force
schtasks /Run /TN GestionFournisseurs
```

**Testez une restauration une fois**, sur une autre machine, avant d'en avoir
besoin. Une sauvegarde jamais restaurée n'est pas une sauvegarde.

---

## 11. Étape 9 — Messagerie et relances

Facultatif. À activer seulement si vous voulez que l'application envoie des
relances aux fournisseurs.

1. **Administration → Paramètres → Messagerie** : serveur SMTP, port, adresse
   d'expédition, compte.
2. Le **mot de passe SMTP ne se saisit pas dans l'interface** — il n'est jamais
   stocké en base. Définissez-le au niveau machine :

```powershell
[Environment]::SetEnvironmentVariable("SMTP_PASSWORD","le-mot-de-passe","Machine")
schtasks /End /TN GestionFournisseurs
schtasks /Run /TN GestionFournisseurs
```

3. Bouton **« Envoyer un message de test »** pour vérifier.
4. Renseignez l'adresse de courriel de chaque fournisseur dans sa fiche.
5. Essai à blanc, qui affiche ce qui partirait sans rien envoyer :

```
cd C:\Applications\gestion-fournisseurs
set DATA_DIR=C:\ProgramData\GestionFournisseurs
.venv\Scripts\python.exe scripts\relances.py --simulation
```

6. Automatisez comme pour la sauvegarde : Planificateur de tâches, tous les
   jours à 8h, `powershell.exe` avec pour arguments
   `-Command "cd C:\Applications\gestion-fournisseurs; $env:DATA_DIR='C:\ProgramData\GestionFournisseurs'; .\.venv\Scripts\python.exe scripts\relances.py"`.

Un fournisseur n'est pas relancé deux fois sur le même sujet à moins de 14 jours
d'intervalle, réglable dans les paramètres.

---

## 12. Étape 10 — Passer en HTTPS

À faire avant l'usage durable. En HTTP, les mots de passe traversent le réseau
en clair et n'importe qui sur le même réseau peut les lire.

### Solution simple : Caddy

Caddy est un serveur web d'un seul fichier exécutable, qui gère les certificats
tout seul.

1. Téléchargez Caddy pour Windows depuis <https://caddyserver.com/download> et
   placez `caddy.exe` dans `C:\Applications\caddy\`.
2. Créez `C:\Applications\caddy\Caddyfile` :

```
gestion.votreorganisation.local {
    tls internal
    reverse_proxy 127.0.0.1:8000
}
```

3. Installez Caddy en service :

```powershell
cd C:\Applications\caddy
.\caddy.exe run --config Caddyfile
```

4. Une fois que cela fonctionne, refermez le port 8000 au réseau et ouvrez le
   443 :

```powershell
Get-NetFirewallRule -DisplayName "Gestion fournisseurs*" | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "Gestion fournisseurs HTTPS" -Direction Inbound `
    -Protocol TCP -LocalPort 443 -Action Allow -Profile Domain,Private
```

5. Indiquez à l'application qu'elle est derrière du HTTPS :

```powershell
[Environment]::SetEnvironmentVariable("COOKIE_SECURE","1","Machine")
schtasks /End /TN GestionFournisseurs; schtasks /Run /TN GestionFournisseurs
```

`tls internal` génère un certificat local ; les navigateurs afficheront un
avertissement tant que l'autorité de Caddy n'est pas distribuée aux postes par
stratégie de groupe. Un certificat émis par l'autorité interne de votre
organisation, s'il en existe une, évite cet avertissement.

### Autre voie

Si vous avez déjà IIS avec un certificat, configurez-le en reverse proxy vers
`http://127.0.0.1:8000` avec le module ARR. Le résultat est le même.

---

## 13. Exploitation au quotidien

| Action | Commande (PowerShell en administrateur) |
|---|---|
| État | `schtasks /Query /TN GestionFournisseurs` |
| Détail complet | `schtasks /Query /TN GestionFournisseurs /V /FO LIST` |
| Arrêter | `schtasks /End /TN GestionFournisseurs` |
| Démarrer | `schtasks /Run /TN GestionFournisseurs` |
| Redémarrer | `schtasks /End /TN GestionFournisseurs; schtasks /Run /TN GestionFournisseurs` |
| Journal technique | `notepad C:\ProgramData\GestionFournisseurs\service.log` |
| Suivre le journal | `Get-Content C:\ProgramData\GestionFournisseurs\service.log -Wait -Tail 30` |
| Vérifier la réponse | `Invoke-RestMethod http://127.0.0.1:8000/sante` |
| Taille des données | `Get-ChildItem C:\ProgramData\GestionFournisseurs -Recurse \| Measure-Object Length -Sum` |

Redémarrez le service après toute modification d'une variable d'environnement :
elles ne sont lues qu'au démarrage.

**Qui a fait quoi** ne se cherche pas dans `service.log` mais dans
l'application : **Administration → Journal d'audit** recense connexions,
créations, modifications, approbations, relances, avec l'utilisateur,
l'horodatage et l'adresse IP.

---

## 14. Mise à jour de l'application

```powershell
# 1. Sauvegarder d'abord, toujours
cd C:\Applications\gestion-fournisseurs
.\windows\sauvegarde.ps1

# 2. Arrêter
schtasks /End /TN GestionFournisseurs

# 3. Remplacer le code, jamais les données
Expand-Archive nouvelle-version.zip -DestinationPath C:\Temp\nouvelle
Copy-Item C:\Temp\nouvelle\gestion-fournisseurs\app     -Destination . -Recurse -Force
Copy-Item C:\Temp\nouvelle\gestion-fournisseurs\scripts -Destination . -Recurse -Force
Copy-Item C:\Temp\nouvelle\gestion-fournisseurs\windows -Destination . -Recurse -Force

# 4. Mettre à jour les composants si requirements.txt a changé
.venv\Scripts\pip install -r requirements.txt --quiet

# 5. Redémarrer
schtasks /Run /TN GestionFournisseurs
Invoke-RestMethod http://127.0.0.1:8000/sante
```

Les colonnes ajoutées par une nouvelle version sont créées automatiquement au
démarrage, sans perte de données.

**Ne touchez jamais au dossier `C:\ProgramData\GestionFournisseurs`** lors d'une
mise à jour. C'est ce qui sépare le code, remplaçable, des données, qui ne le
sont pas.

---

## 15. Dépannage

### « python n'est pas reconnu »

La case « Add python.exe to PATH » n'a pas été cochée. Relancez l'installateur
Python, choisissez « Modify », cochez « Add Python to environment variables ».
Fermez et rouvrez toutes les fenêtres de commandes.

### Le script PowerShell ne démarre pas

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
```

puis relancez dans la même fenêtre. Ne modifiez pas la politique globale de la
machine.

### La fenêtre noire se ferme aussitôt

Une erreur s'affiche trop vite pour être lue. Ouvrez une invite de commandes,
puis lancez le script depuis là pour voir le message :

```
cd C:\Applications\gestion-fournisseurs
demarrer-windows.bat
```

### « Le port est déjà utilisé »

Trouvez le coupable :

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Get-Process -Id <numéro affiché>
```

Soit vous arrêtez ce programme, soit vous réinstallez sur un autre port :
`.\windows\installer-service.ps1 -Port 8080`.

### Rien ne répond après un redémarrage du PC

```powershell
schtasks /Query /TN GestionFournisseurs /V /FO LIST
```

Regardez « Dernier résultat d'exécution ». Puis consultez
`C:\ProgramData\GestionFournisseurs\service.log`, qui contient l'erreur exacte.
Cause fréquente : le dossier de données a été déplacé ou ses droits ont changé.

### Inaccessible depuis un autre poste

Dans l'ordre :

```powershell
# 1. L'application répond-elle localement ?
Invoke-RestMethod http://127.0.0.1:8000/sante

# 2. Écoute-t-elle sur le réseau, ou seulement en local ?
Get-NetTCPConnection -LocalPort 8000 | Select-Object LocalAddress
#    0.0.0.0 = bon ; 127.0.0.1 = installé avec -LocalUniquement

# 3. La règle de pare-feu existe-t-elle ?
Get-NetFirewallRule -DisplayName "Gestion fournisseurs*" | Format-List DisplayName,Enabled,Profile

# 4. Le réseau est-il classé « Public » ? La règle ne couvre pas ce profil.
Get-NetConnectionProfile
```

Pour basculer le réseau en « Privé » :

```powershell
Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private
```

### Déconnexion à chaque rafraîchissement de page

La clé de session change à chaque démarrage. Vérifiez qu'elle est bien définie :

```powershell
[Environment]::GetEnvironmentVariable("SECRET_KEY","Machine")
```

Si la commande ne renvoie rien, relancez le script d'installation.

### « Impossible de se connecter » alors que le mot de passe est bon

Le compte est peut-être verrouillé : cinq échecs déclenchent un blocage de
quinze minutes. Attendez, ou depuis un autre compte administrateur faites
Administration → Utilisateurs → Modifier, ce qui lève le verrou.

Si c'est le compte `admin` qui est bloqué et qu'il n'y a pas d'autre
administrateur, attendez simplement les quinze minutes.

### Reprendre les données de l'essai de l'étape 3

```powershell
schtasks /End /TN GestionFournisseurs
Copy-Item C:\Applications\gestion-fournisseurs\data\gestion.db `
          C:\ProgramData\GestionFournisseurs\gestion.db -Force
schtasks /Run /TN GestionFournisseurs
```

Les comptes et mots de passe de l'essai sont repris avec la base.

### Une pièce jointe est refusée

Formats acceptés : PDF, JPEG, PNG, WEBP, TIFF. 10 Mo maximum. L'application
vérifie aussi que le contenu correspond à l'extension : un fichier renommé en
`.pdf` sera rejeté.

### Le service tourne mais la page reste blanche

Videz le cache du navigateur (Ctrl-Maj-R). Si le problème persiste, ouvrez la
console du navigateur (F12) et regardez les erreurs.

---

## 16. Poste sans accès internet

L'installation a besoin d'internet une seule fois, pour télécharger Flask,
waitress et openpyxl. Si la machine cible est isolée :

**Sur une machine connectée**, avec la même version de Python et Windows 64 bits :

```powershell
cd C:\Applications\gestion-fournisseurs
pip download -r requirements.txt -d composants --platform win_amd64 `
    --python-version 312 --only-binary :all:
```

Copiez le dossier `composants` dans l'application sur la machine cible, puis :

```powershell
cd C:\Applications\gestion-fournisseurs
python -m venv .venv
.venv\Scripts\pip install --no-index --find-links composants -r requirements.txt
.venv\Scripts\pip install --no-index --find-links composants waitress
```

L'installateur détecte ensuite l'environnement déjà prêt et ne tente aucun
téléchargement. N'oubliez pas de transférer aussi l'installateur Python
lui-même.

---

## 17. Tout désinstaller

```powershell
cd C:\Applications\gestion-fournisseurs
.\windows\desinstaller-service.ps1
```

Le script retire la tâche planifiée et la règle de pare-feu. **Il ne supprime
pas vos données** : elles restent dans `C:\ProgramData\GestionFournisseurs`.

Pour tout effacer définitivement, après avoir mis vos sauvegardes en lieu sûr :

```powershell
Remove-Item C:\ProgramData\GestionFournisseurs -Recurse -Force
Remove-Item C:\Applications\gestion-fournisseurs -Recurse -Force
[Environment]::SetEnvironmentVariable("SECRET_KEY",$null,"Machine")
[Environment]::SetEnvironmentVariable("DATA_DIR",$null,"Machine")
```

---

## 18. Aide-mémoire

À imprimer et coller près de la machine.

```
APPLICATION   C:\Applications\gestion-fournisseurs
DONNÉES       C:\ProgramData\GestionFournisseurs      <- le seul dossier à sauvegarder
ADRESSE       http://__________________:8000
TÂCHE         GestionFournisseurs
JOURNAL       C:\ProgramData\GestionFournisseurs\service.log

ARRÊTER       schtasks /End /TN GestionFournisseurs
DÉMARRER      schtasks /Run /TN GestionFournisseurs
ÉTAT          schtasks /Query /TN GestionFournisseurs
SANTÉ         Invoke-RestMethod http://127.0.0.1:8000/sante
SAUVEGARDER   C:\Applications\gestion-fournisseurs\windows\sauvegarde.ps1
```

### Liste de contrôle avant la mise en production

- [ ] La machine reste allumée, veille désactivée
- [ ] Adresse IP fixe ou réservation DHCP
- [ ] Mot de passe `admin` changé
- [ ] `MOT_DE_PASSE_INITIAL.txt` supprimé
- [ ] Un compte nominatif par utilisateur, aucun compte partagé
- [ ] Rôles vérifiés, notamment la séparation demande / approbation
- [ ] Seuil du devis comparatif et validité du C20 conformes à vos règles
- [ ] Sauvegarde quotidienne planifiée **et** copiée hors de la machine
- [ ] Une restauration testée au moins une fois
- [ ] HTTPS en place, `COOKIE_SECURE=1`
- [ ] Redémarrage du PC testé : l'application repart seule
- [ ] Pare-feu limité aux profils Domaine et Privé
