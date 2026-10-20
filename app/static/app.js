/* Interface de gestion des fournisseurs et des paiements.
   Tout contrôle réel est fait côté serveur ; l'interface se contente de
   masquer ce que l'utilisateur ne peut pas faire. */
"use strict";

const S = {
  session: null,          // {utilisateur, permissions, modules, parametres, csrf}
  data: null,             // réponse de /api/data
  admin: {},              // caches des écrans d'administration
  module: "tableau",
  filtres: {mois: "", dept: "", fourn: "", q: ""},
  devisForm: null,
};

/* ---------------- utilitaires ---------------- */
const $ = (sel) => document.querySelector(sel);
function esc(v){
  return String(v == null ? "" : v).replace(/[&<>"']/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function can(p){ return !!(S.session && S.session.permissions.includes(p)); }
function param(k, def){ return (S.session && S.session.parametres[k]) || def; }
function devise(){ return param("devise", "DZD"); }
function nombre(n){ return new Intl.NumberFormat("fr-FR").format(Math.round(Number(n) || 0)); }
function montant(n){ return nombre(n) + " " + devise(); }
function dateFr(iso){
  if(!iso) return "";
  const p = String(iso).slice(0, 10).split("-");
  return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(iso);
}
function horodate(iso){
  if(!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("fr-FR", {dateStyle: "short", timeStyle: "short"});
}
function chip(txt, tone){ return '<span class="chip ' + (tone || "neutral") + '">' + esc(txt) + "</span>"; }
function toast(msg, err){
  $("#toast").innerHTML = '<div class="toast' + (err ? " err" : "") + '">' + esc(msg) + "</div>";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { $("#toast").innerHTML = ""; }, err ? 5200 : 2800);
}
function aujourdhui(){ return new Date().toISOString().slice(0, 10); }

/* ---------------- accès API ---------------- */
async function api(method, path, body){
  const opts = {method, headers: {"Content-Type": "application/json"}, credentials: "same-origin"};
  if(S.session && S.session.csrf) opts.headers["X-CSRF-Token"] = S.session.csrf;
  if(body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if(res.status === 401 && S.session && S.session.authenticated){
    S.session = null; render();
    throw new Error("Session expirée. Reconnectez-vous.");
  }
  let payload = null;
  try { payload = await res.json(); } catch(e){ payload = null; }
  if(!res.ok) throw new Error((payload && payload.error) || "Erreur " + res.status);
  return payload;
}
async function apiFichier(path, formData){
  const res = await fetch(path, {method: "POST", body: formData, credentials: "same-origin",
                                 headers: {"X-CSRF-Token": (S.session && S.session.csrf) || ""}});
  let payload = null;
  try { payload = await res.json(); } catch(e){ payload = null; }
  if(!res.ok) throw new Error((payload && payload.error) || "Erreur " + res.status);
  return payload;
}

async function rafraichir(){
  S.data = await api("GET", "/api/data");
  render();
}

/* ---------------- démarrage ---------------- */
async function demarrer(){
  try{
    const sess = await fetch("/api/auth/session", {credentials: "same-origin"}).then(r => r.json());
    S.session = sess;
    if(sess.authenticated){
      S.module = (sess.modules[0] || {}).code || "tableau";
      await rafraichir();
    } else {
      render();
    }
  } catch(e){
    document.getElementById("racine").innerHTML =
      '<div class="login"><div class="login-card"><h1>Serveur injoignable</h1>' +
      '<p class="sub">' + esc(e.message) + "</p></div></div>";
  }
}

/* ---------------- rendu principal ---------------- */
function render(){
  if(!S.session || !S.session.authenticated){ renderLogin(); return; }
  const modules = S.session.modules;
  if(!modules.some(m => m.code === S.module)) S.module = (modules[0] || {}).code || "tableau";
  const courant = modules.find(m => m.code === S.module) || {nom: "", code: ""};
  const u = S.session.utilisateur;

  document.getElementById("racine").innerHTML =
    '<div class="shell"><aside class="rail">' +
      '<div class="brand"><h1>' + esc(param("org_name", "Gestion fournisseurs")) + "</h1>" +
      "<p>Dossiers fiscaux, bons de commande, factures et paiements</p></div>" +
      '<nav class="nav">' + navHtml(modules) + "</nav>" +
      '<div class="railfoot"><div><span class="nom">' + esc(u.nom) + "</span><br>" +
        esc(u.role) + "</div>" +
        '<div class="actions">' +
          '<button class="btn small" data-act="mdp">Mot de passe</button>' +
          '<button class="btn small" data-act="logout">Déconnexion</button>' +
        "</div></div>" +
    "</aside><main class=\"main\">" + entete(courant) + corps() + "</main></div>";

  if(u.must_change) formulaireMotDePasse(true);
}

function navHtml(modules){
  const metier = modules.filter(m => !["utilisateurs","roles","referentiels","journal","parametres"].includes(m.code));
  const admin = modules.filter(m => ["utilisateurs","roles","referentiels","journal","parametres"].includes(m.code));
  const bouton = (m) => {
    let badge = "";
    const i = (S.data && S.data.indicateurs) || {};
    if(m.code === "fournisseurs" && i.dossiers_incomplets) badge = '<span class="count flag">' + i.dossiers_incomplets + "</span>";
    else if(m.code === "devis" && i.devis_non_conformes) badge = '<span class="count flag">' + i.devis_non_conformes + "</span>";
    else if(m.code === "validation" && i.demandes_en_attente) badge = '<span class="count flag">' + i.demandes_en_attente + "</span>";
    else if(m.code === "paiements" && i.nb_a_payer) badge = '<span class="count">' + i.nb_a_payer + "</span>";
    else if(m.code === "bons" && i.nb_bons) badge = '<span class="count">' + i.nb_bons + "</span>";
    return '<button data-mod="' + m.code + '" aria-current="' + (S.module === m.code) + '">' +
      '<span class="ico" aria-hidden="true">' + m.ico + "</span>" + esc(m.nom) + badge + "</button>";
  };
  let h = metier.map(bouton).join("");
  if(admin.length) h += '<div class="sep">Administration</div>' + admin.map(bouton).join("");
  return h;
}

const DESCRIPTIONS = {
  tableau: "Ce qui bloque un paiement aujourd'hui, par ordre d'urgence.",
  fournisseurs: "Un fournisseur, une ligne permanente. L'expiration du C20 et l'alerte sont calculées par le serveur.",
  bons: "Un bon de commande appartient au mois de sa création et n'en change plus.",
  factures: "Réception des factures originales et délai entre facture et paiement.",
  paiements: "Règlements par chèque ou virement, et suivi du débit en banque.",
  devis: "Au-delà du seuil paramétré, un devis comparatif daté et signé est exigé.",
  validation: "Demandes de mise en paiement, et décision d'approbation ou de refus.",
  pieces: "Documents numérisés rattachés aux fournisseurs et aux bons de commande.",
  relances: "Courriels envoyés aux fournisseurs, automatiquement ou à la demande.",
  utilisateurs: "Comptes autorisés à se connecter et rôle attribué à chacun.",
  roles: "Ce que chaque rôle peut voir et modifier, permission par permission.",
  referentiels: "Départements émetteurs de bons de commande.",
  journal: "Toutes les écritures et connexions, dans l'ordre chronologique inverse.",
  parametres: "Seuil du devis comparatif, validité du C20 et délais d'alerte.",
};
function entete(m){
  return '<div class="topbar"><div><h2>' + esc(m.nom) + "</h2><p>" +
    esc(DESCRIPTIONS[m.code] || "") + "</p></div>" +
    '<div class="actions">' + boutonsEntete() + "</div></div>";
}
function boutonsEntete(){
  let h = "";
  if(S.module === "fournisseurs" && can("fournisseurs.edit"))
    h += '<button class="btn primary" data-act="new-f">Ajouter un fournisseur</button>';
  if(["bons","factures","paiements"].includes(S.module) && can("bons.edit"))
    h += '<button class="btn primary" data-act="new-b">Ajouter un bon de commande</button>';
  if(S.module === "utilisateurs" && can("admin.users"))
    h += '<button class="btn primary" data-act="new-u">Créer un compte</button>';
  if(S.module === "roles" && can("admin.roles"))
    h += '<button class="btn primary" data-act="new-r">Créer un rôle</button>';
  if(S.module === "referentiels" && can("admin.departments"))
    h += '<button class="btn primary" data-act="new-d">Ajouter un département</button>';
  if(S.module === "relances" && can("relances.send"))
    h += '<button class="btn" data-act="test-mail">Envoyer un message de test</button>';
  if(["fournisseurs","bons","factures","paiements","devis"].includes(S.module) && can("export.csv"))
    h += '<a class="btn" href="/api/export/' + S.module + '.csv">Exporter en CSV</a>';
  return h;
}

function corps(){
  const vues = {
    tableau: vueTableau, fournisseurs: vueFournisseurs, bons: vueBons,
    factures: vueFactures, paiements: vuePaiements, devis: vueDevis,
    validation: vueValidation, pieces: vuePieces, relances: vueRelances,
    utilisateurs: vueUtilisateurs, roles: vueRoles, referentiels: vueDepartements,
    journal: vueJournal, parametres: vueParametres,
  };
  if(!S.data) return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>';
  if(["fournisseurs","bons","factures","paiements","devis","tableau","validation"].includes(S.module)
     && !S.data.fournisseurs.length && !S.data.bons.length)
    return vueVide();
  return (vues[S.module] || (() => ""))();
}

function vueVide(){
  let h = '<div class="panel"><div class="empty"><h4>La base est vide</h4>' +
    "<p>Commencez par référencer vos fournisseurs et leurs pièces fiscales.</p>" +
    '<div class="actions" style="justify-content:center">';
  if(can("fournisseurs.edit")) h += '<button class="btn primary" data-act="new-f">Ajouter un fournisseur</button>';
  if(can("admin.settings")) h += '<button class="btn" data-act="demo">Charger le jeu d\'essai</button>';
  return h + "</div></div></div>";
}

/* ---------------- filtres ---------------- */
function filtresHtml(){
  const bons = S.data.bons;
  const mois = Array.from(new Set(bons.map(b => b.mois).filter(Boolean))).sort().reverse();
  const labels = {};
  bons.forEach(b => { labels[b.mois] = b.mois_label; });
  const fournisseurs = Array.from(new Set(bons.map(b => b.supplier_name))).sort();
  let h = '<div class="filters">';
  h += '<select data-filtre="mois"><option value="">Tous les mois</option>' +
    mois.map(m => '<option value="' + m + '"' + (S.filtres.mois === m ? " selected" : "") + ">" +
      esc(labels[m] || m) + "</option>").join("") + "</select>";
  h += '<select data-filtre="dept"><option value="">Tous les départements</option>' +
    S.data.departements.map(d => '<option value="' + esc(d) + '"' +
      (S.filtres.dept === d ? " selected" : "") + ">" + esc(d) + "</option>").join("") + "</select>";
  h += '<select data-filtre="fourn"><option value="">Tous les fournisseurs</option>' +
    fournisseurs.map(d => '<option value="' + esc(d) + '"' +
      (S.filtres.fourn === d ? " selected" : "") + ">" + esc(d) + "</option>").join("") + "</select>";
  h += '<input type="search" data-filtre="q" placeholder="N° de BC, facture, prestation…" value="' +
    esc(S.filtres.q) + '">';
  if(S.filtres.mois || S.filtres.dept || S.filtres.fourn || S.filtres.q)
    h += '<button class="btn small" data-act="reset-filtres">Effacer</button>';
  return h + "</div>";
}
function bonsFiltres(){
  const f = S.filtres;
  return S.data.bons.filter(b => {
    if(f.mois && b.mois !== f.mois) return false;
    if(f.dept && b.department !== f.dept) return false;
    if(f.fourn && b.supplier_name !== f.fourn) return false;
    if(f.q){
      const t = [b.po_number, b.supplier_name, b.description, b.invoice_number,
                 b.cheque_number, b.transfer_number].join(" ").toLowerCase();
      if(!t.includes(f.q.toLowerCase())) return false;
    }
    return true;
  });
}

/* ---------------- tableau de bord ---------------- */
function fig(v, k, tone){
  return '<div class="fig"><div class="v ' + (tone || "") + '">' + esc(v) +
    '</div><div class="k">' + esc(k) + "</div></div>";
}
function vueTableau(){
  const i = S.data.indicateurs || {};
  const travail = S.data.travail || [];
  let h = '<div class="panel"><div class="figs">' +
    fig(montant(i.engage), "Engagé sur " + i.nb_bons + " bons de commande") +
    fig(montant(i.montant_a_payer), i.nb_a_payer + " bons restant à payer", i.nb_a_payer ? "warn" : "ok") +
    fig(String(i.nb_attente_debit), "Paiements en attente de débit") +
    fig(String(i.dossiers_incomplets), "Dossiers fiscaux incomplets", i.dossiers_incomplets ? "danger" : "ok") +
    fig(String(i.devis_non_conformes), "Devis comparatifs à régulariser", i.devis_non_conformes ? "danger" : "ok") +
    (i.demandes_en_attente !== undefined
      ? fig(String(i.demandes_en_attente), "Règlements à approuver", i.demandes_en_attente ? "warn" : "ok") : "") +
    "</div></div>";

  h += '<div class="panel"><div class="panel-head"><h3>À traiter</h3><span class="sub">' +
    travail.length + " point" + (travail.length > 1 ? "s" : "") + " de contrôle</span></div>";
  if(!travail.length)
    h += '<div class="empty"><h4>Rien ne bloque</h4><p>Les dossiers fiscaux sont à jour et les bons de commande sont conformes.</p></div>';
  else
    h += '<ul class="work">' + travail.slice(0, 40).map(x =>
      '<li class="' + x.tone + '"><div class="txt"><div class="t">' + esc(x.titre) +
      '</div><div class="d">' + esc(x.detail) + "</div></div>" +
      '<div><button class="btn small" data-mod="' + x.module + '">Ouvrir</button></div></li>').join("") + "</ul>";
  h += "</div>";

  h += '<div class="panel"><div class="panel-head"><h3>Par mois de bon de commande</h3></div>' +
    '<div class="tablewrap"><table><thead><tr><th>Mois</th><th class="num">Bons</th>' +
    '<th class="num">Total TTC</th><th class="num">Réglé</th><th class="num">Reste à payer</th></tr></thead><tbody>' +
    (S.data.par_mois || []).map(m => "<tr><td>" + esc(m.label) + '</td><td class="num">' + m.nb +
      '</td><td class="num">' + montant(m.ttc) + '</td><td class="num">' + montant(m.regle) +
      '</td><td class="num">' + (m.reste ? montant(m.reste) : '<span class="muted">—</span>') +
      "</td></tr>").join("") + "</tbody></table></div></div>";
  return h;
}

/* ---------------- dossiers fiscaux ---------------- */
function vueFournisseurs(){
  const list = S.data.fournisseurs;
  if(!list.length) return '<div class="panel"><div class="empty"><h4>Aucun fournisseur référencé</h4>' +
    "<p>Chaque fournisseur est une ligne permanente : identifiants fiscaux, RIB et C20.</p></div></div>";
  let h = '<div class="panel"><div class="panel-head"><h3>' + list.length + " fournisseurs</h3>" +
    '<span class="sub">Le C20 est valable ' + param("c20_validite_mois", "12") +
    " mois ; l'expiration et l'alerte sont calculées.</span></div>" +
    '<div class="tablewrap"><table><thead><tr><th>Fournisseur</th><th>Département</th><th>NIF</th>' +
    "<th>RC / agrément</th><th>RIB</th><th>Date du C20</th><th>Expiration</th><th>Alerte C20</th>" +
    "<th>Dossier</th>" + (can("pieces.view") ? "<th>Pièces</th>" : "") + "<th></th></tr></thead><tbody>";
  for(const f of list){
    const a = f.c20_alerte;
    const cls = a.tone === "danger" ? "r-danger" : f.statut_dossier !== "Complet" ? "r-warn" : "r-ok";
    const manquant = '<span class="chip danger">manquant</span>';
    h += '<tr class="' + cls + '">' +
      "<td><strong>" + esc(f.name) + "</strong></td>" +
      "<td>" + esc(f.department) + "</td>" +
      "<td>" + (f.nif ? esc(f.nif) : manquant) + "</td>" +
      "<td>" + (f.rc ? esc(f.rc) : manquant) + "</td>" +
      "<td>" + (f.rib ? esc(f.rib) : manquant) + "</td>" +
      "<td>" + (f.c20_date ? dateFr(f.c20_date) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + (f.c20_expiration ? dateFr(f.c20_expiration) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + chip(a.label, a.tone) + "</td>" +
      "<td>" + chip(f.statut_dossier, f.statut_dossier === "Complet" ? "ok" : "warn") +
        (f.pieces_manquantes.length ? '<div class="muted" style="font-size:12px;margin-top:2px">' +
          esc(f.pieces_manquantes.join(", ")) + "</div>" : "") + "</td>" +
      (can("pieces.view") ? "<td>" + (f.nb_pieces
          ? chip(f.nb_pieces + " pièce" + (f.nb_pieces > 1 ? "s" : ""), "primary")
          : '<span class="muted">—</span>') + "</td>" : "") +
      "<td>" + '<button class="btn small" data-edit-f="' + f.id + '">' +
        (can("fournisseurs.edit") ? "Modifier" : "Consulter") + "</button>" +
        (can("relances.send") && f.statut_dossier !== "Complet" && f.email
          ? ' <button class="btn small" data-relance-f="' + f.id + '">Relancer</button>' : "") +
      "</td></tr>";
  }
  return h + "</tbody></table></div></div>";
}

/* ---------------- bons de commande ---------------- */
function vueBons(){
  const list = bonsFiltres();
  const total = list.reduce((s, b) => s + Number(b.amount_ttc || 0), 0);
  let h = '<div class="panel"><div class="panel-head">' + filtresHtml() + "</div>" +
    '<div class="panel-head" style="border-top:0"><h3>' + list.length +
    " bons de commande</h3><span class=\"sub\">Total affiché : " + montant(total) + "</span></div>";
  if(!list.length) return h + '<div class="empty"><p>Aucun bon de commande ne correspond à ces filtres.</p></div></div>';
  h += '<div class="tablewrap"><table><thead><tr><th>Date</th><th>N° BC</th><th>Département</th>' +
    '<th>Fournisseur</th><th>Prestation</th><th class="num">Montant TTC</th><th>Devis comparatif</th>' +
    "<th>Dossier fiscal</th><th>Paiement</th><th></th></tr></thead><tbody>";
  for(const b of list){
    const cls = b.devis_etat.code === "ko" ? "r-seuil" : b.dossier_fiscal.code !== "ok" ? "r-warn" : "";
    h += '<tr class="' + cls + '">' +
      "<td>" + dateFr(b.po_date) + "</td>" +
      "<td><strong>" + esc(b.po_number) + "</strong></td>" +
      "<td>" + esc(b.department) + "</td>" +
      "<td>" + esc(b.supplier_name) + "</td>" +
      '<td class="wrapcell">' + esc(b.description) + "</td>" +
      '<td class="num"><strong>' + montant(b.amount_ttc) + "</strong>" +
        (b.devis_requis ? '<div style="font-size:11.5px;color:var(--seuil);font-weight:600">≥ seuil</div>' : "") + "</td>" +
      "<td>" + chip(b.devis_etat.label, b.devis_etat.tone) + "</td>" +
      "<td>" + chip(b.dossier_fiscal.label, b.dossier_fiscal.tone) + "</td>" +
      "<td>" + chip(b.statut_paiement, tonePaiement(b.statut_paiement)) + "</td>" +
      '<td><button class="btn small" data-edit-b="' + b.id + '">' +
        (peutModifierBon() ? "Modifier" : "Consulter") + "</button></td></tr>";
  }
  return h + "</tbody></table></div></div>";
}
function tonePaiement(st){
  return st === "Payé et débité" ? "ok" : st === "Payé – en attente de débit" ? "warn" : "neutral";
}
function peutModifierBon(){
  return can("bons.edit") || can("factures.edit") || can("paiements.edit") || can("devis.edit");
}

/* ---------------- factures ---------------- */
function vueFactures(){
  const list = bonsFiltres();
  const manquantes = list.filter(b => !b.invoice_number || b.invoice_status === "Facture non remise");
  let h = '<div class="panel"><div class="figs">' +
    fig(String(list.length), "Factures suivies") +
    fig(String(manquantes.length), "Originaux non remis", manquantes.length ? "warn" : "ok") +
    fig(moyenne(list.map(b => b.delai_facture_paiement)), "Jours en moyenne, facture → paiement") +
    "</div></div>";
  h += '<div class="panel"><div class="panel-head">' + filtresHtml() + "</div>";
  if(!list.length) return h + '<div class="empty"><p>Aucune facture ne correspond à ces filtres.</p></div></div>';
  h += '<div class="tablewrap"><table><thead><tr><th>N° facture</th><th>Date facture</th><th>N° BC</th>' +
    '<th>Fournisseur</th><th class="num">Montant TTC</th><th>État de l\'original</th>' +
    '<th class="num">Facture → paiement</th><th>Paiement</th><th></th></tr></thead><tbody>';
  for(const b of list){
    const remise = b.invoice_status === "Facture remise";
    h += '<tr class="' + (remise ? "" : "r-warn") + '">' +
      "<td><strong>" + (b.invoice_number ? esc(b.invoice_number) : '<span class="muted">non reçue</span>') + "</strong></td>" +
      "<td>" + (b.invoice_date ? dateFr(b.invoice_date) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + esc(b.po_number) + "</td>" +
      "<td>" + esc(b.supplier_name) + "</td>" +
      '<td class="num">' + montant(b.amount_ttc) + "</td>" +
      "<td>" + (b.invoice_status ? chip(b.invoice_status, remise ? "ok" : "warn") : '<span class="muted">—</span>') + "</td>" +
      '<td class="num">' + (b.delai_facture_paiement == null ? '<span class="muted">—</span>' : b.delai_facture_paiement + " j") + "</td>" +
      "<td>" + chip(b.statut_paiement, tonePaiement(b.statut_paiement)) + "</td>" +
      '<td><button class="btn small" data-edit-b="' + b.id + '">' +
        (can("factures.edit") ? "Modifier" : "Consulter") + "</button></td></tr>";
  }
  return h + "</tbody></table></div></div>";
}
function moyenne(arr){
  const v = arr.filter(x => x != null);
  return v.length ? String(Math.round(v.reduce((a, b) => a + b, 0) / v.length)) : "—";
}

/* ---------------- paiements ---------------- */
function vuePaiements(){
  const list = bonsFiltres();
  const somme = (arr) => arr.reduce((s, b) => s + Number(b.amount_ttc || 0), 0);
  const aPayer = list.filter(b => b.statut_paiement === "À payer");
  const attente = list.filter(b => b.statut_paiement === "Payé – en attente de débit");
  const debite = list.filter(b => b.statut_paiement === "Payé et débité");
  let h = '<div class="panel"><div class="figs">' +
    fig(montant(somme(aPayer)), aPayer.length + " à payer", aPayer.length ? "warn" : "ok") +
    fig(montant(somme(attente)), attente.length + " payés, en attente de débit") +
    fig(montant(somme(debite)), debite.length + " payés et débités", "ok") +
    fig(moyenne(list.map(b => b.delai_paiement_debit)), "Jours en moyenne, paiement → débit") +
    "</div></div>";
  h += '<div class="panel"><div class="panel-head">' + filtresHtml() + "</div>";
  if(!list.length) return h + '<div class="empty"><p>Aucun paiement ne correspond à ces filtres.</p></div></div>';
  h += '<div class="tablewrap"><table><thead><tr><th>Mois du BC</th><th>N° BC</th><th>Fournisseur</th>' +
    '<th class="num">Montant TTC</th><th>Mode</th><th>N° chèque / ordre</th><th>Date de paiement</th>' +
    '<th>Date de débit</th><th class="num">Délai</th><th>Statut</th><th></th></tr></thead><tbody>';
  for(const b of list){
    const ref = b.payment_mode === "Chèque" ? b.cheque_number : b.transfer_number;
    const bloque = b.devis_etat.code === "ko" || b.dossier_fiscal.code !== "ok";
    const cls = b.statut_paiement === "À payer" ? (bloque ? "r-danger" : "r-warn")
              : b.statut_paiement === "Payé et débité" ? "r-ok" : "";
    h += '<tr class="' + cls + '">' +
      "<td>" + esc(b.mois_label) + "</td>" +
      "<td><strong>" + esc(b.po_number) + "</strong></td>" +
      "<td>" + esc(b.supplier_name) + "</td>" +
      '<td class="num">' + montant(b.amount_ttc) + "</td>" +
      "<td>" + (b.payment_mode ? chip(b.payment_mode, "primary") : '<span class="muted">—</span>') + "</td>" +
      "<td>" + (ref ? esc(ref) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + (b.payment_date ? dateFr(b.payment_date) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + (b.debit_date ? dateFr(b.debit_date) : '<span class="muted">—</span>') + "</td>" +
      '<td class="num">' + (b.delai_paiement_debit == null ? '<span class="muted">—</span>' : b.delai_paiement_debit + " j") + "</td>" +
      "<td>" + chip(b.statut_paiement, tonePaiement(b.statut_paiement)) +
        (bloque && b.statut_paiement === "À payer"
          ? '<div style="font-size:11.5px;color:var(--danger);margin-top:2px">contrôle à lever</div>' : "") + "</td>" +
      '<td><button class="btn small" data-edit-b="' + b.id + '">' +
        (can("paiements.edit") ? "Modifier" : "Consulter") + "</button></td></tr>";
  }
  return h + "</tbody></table></div></div>";
}

/* ---------------- devis comparatifs ---------------- */
function vueDevis(){
  const list = bonsFiltres().filter(b => b.devis_requis);
  const aRegulariser = list.filter(b => b.devis_etat.code !== "ok");
  const seuil = Number(param("seuil_devis", 350000));
  let h = '<div class="panel"><div class="figs">' +
    fig(montant(seuil), "Seuil déclenchant l'obligation") +
    fig(String(list.length), "Bons de commande concernés") +
    fig(String(aRegulariser.length), "Dossiers à compléter ou valider", aRegulariser.length ? "danger" : "ok") +
    "</div></div>";
  h += '<div class="panel"><div class="panel-head">' + filtresHtml() + "</div>";
  if(!list.length) return h + '<div class="empty"><h4>Aucun bon au-dessus du seuil</h4><p>Un devis comparatif devient obligatoire à partir de ' +
    esc(montant(seuil)) + " TTC.</p></div></div>";
  const modifiable = can("devis.edit");
  h += '<div class="tablewrap"><table><thead><tr><th>N° BC</th><th>Date</th><th>Fournisseur</th>' +
    '<th>Prestation</th><th class="num">Montant TTC</th><th>Devis réalisé</th><th>Date de création</th>' +
    "<th>Signé</th><th>Contrôle</th><th>Validation</th></tr></thead><tbody>";
  for(const b of list){
    const e = b.devis_etat;
    h += '<tr class="' + (e.code === "ok" ? "r-ok" : "r-seuil") + '">' +
      "<td><strong>" + esc(b.po_number) + "</strong></td>" +
      "<td>" + dateFr(b.po_date) + "</td>" +
      "<td>" + esc(b.supplier_name) + "</td>" +
      '<td class="wrapcell">' + esc(b.description) + "</td>" +
      '<td class="num">' + montant(b.amount_ttc) + "</td>" +
      '<td><input type="checkbox" data-devis="quote_done" data-id="' + b.id + '"' +
        (b.quote_done ? " checked" : "") + (modifiable ? "" : " disabled") + ' aria-label="Devis comparatif réalisé"></td>' +
      '<td><input type="date" data-devis="quote_date" data-id="' + b.id + '" value="' +
        esc(b.quote_date || "") + '"' + (modifiable ? "" : " disabled") +
        ' style="padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--surface-2)"></td>' +
      '<td><input type="checkbox" data-devis="quote_signed" data-id="' + b.id + '"' +
        (b.quote_signed ? " checked" : "") + (modifiable ? "" : " disabled") + ' aria-label="Devis comparatif signé"></td>' +
      "<td>" + chip(e.label.replace("Devis comparatif : ", ""), e.tone) + "</td>" +
      "<td>" + (b.quote_approved_at
        ? '<span class="muted" style="font-size:12px">' + esc(b.quote_approved_by) + "<br>" + horodate(b.quote_approved_at) + "</span>"
        : (can("devis.approve") && b.quote_done && b.quote_date && b.quote_signed
            ? '<button class="btn small" data-valider="' + b.id + '">Valider</button>'
            : '<span class="muted">—</span>')) + "</td></tr>";
  }
  return h + "</tbody></table></div></div>";
}


/* ---------------- validation des paiements ---------------- */
function vueValidation(){
  const actif = String(param("validation_paiement", "1")) === "1";
  if(!actif)
    return '<div class="panel"><div class="empty"><h4>Circuit de validation désactivé</h4>' +
      "<p>Les règlements se saisissent directement dans le module Paiements. " +
      "Un administrateur peut réactiver le circuit dans les paramètres.</p></div></div>";

  const tous = bonsFiltres();
  const groupes = [
    ["demande",   "En attente d'approbation", "warn"],
    ["refuse",    "Demandes refusées",        "danger"],
    ["brouillon", "Règlements à demander",    "neutral"],
    ["approuve",  "Approuvés pour règlement", "ok"],
  ];
  let h = '<div class="panel"><div class="panel-head">' + filtresHtml() + "</div></div>";

  for(const [code, titre, ton] of groupes){
    let lignes = tous.filter(b => (b.validation || {}).code === code);
    if(code === "brouillon") lignes = lignes.filter(b => b.statut_paiement === "À payer");
    if(code === "approuve")  lignes = lignes.filter(b => b.statut_paiement === "À payer");
    if(!lignes.length) continue;
    const somme = lignes.reduce((s, b) => s + Number(b.amount_ttc || 0), 0);
    h += '<div class="panel"><div class="panel-head"><h3>' + esc(titre) + "</h3>" +
      '<span class="sub">' + lignes.length + " bon(s) · " + montant(somme) + "</span></div>" +
      '<div class="tablewrap"><table><thead><tr><th>N° BC</th><th>Date</th><th>Fournisseur</th>' +
      '<th>Prestation</th><th class="num">Montant TTC</th><th>Contrôles</th><th>Suivi</th>' +
      "<th></th></tr></thead><tbody>";
    for(const b of lignes){
      const bloc = b.blocages || [];
      h += '<tr class="r-' + ton + '">' +
        "<td><strong>" + esc(b.po_number) + "</strong></td>" +
        "<td>" + dateFr(b.po_date) + "</td>" +
        "<td>" + esc(b.supplier_name) + "</td>" +
        '<td class="wrapcell">' + esc(b.description) + "</td>" +
        '<td class="num"><strong>' + montant(b.amount_ttc) + "</strong></td>" +
        "<td>" + (bloc.length
          ? bloc.map(m => chip(m, "danger")).join(" ")
          : chip("Aucun blocage", "ok")) + "</td>" +
        '<td class="wrapcell muted" style="font-size:12px">' + suiviValidation(b) + "</td>" +
        "<td>" + actionsValidation(b) + "</td></tr>";
    }
    h += "</tbody></table></div></div>";
  }
  if(h.indexOf("<tbody>") === -1)
    h += '<div class="panel"><div class="empty"><h4>Aucune demande en cours</h4>' +
      "<p>Les bons de commande réglés ou sans demande ouverte n'apparaissent pas ici.</p></div></div>";
  return h;
}
function suiviValidation(b){
  const morceaux = [];
  if(b.pay_requested_by) morceaux.push("Demandé par " + esc(b.pay_requested_by) +
    (b.pay_requested_at ? " le " + horodate(b.pay_requested_at) : ""));
  if(b.pay_decided_by) morceaux.push((b.validation.code === "approuve" ? "Approuvé" : "Refusé") +
    " par " + esc(b.pay_decided_by) + (b.pay_decided_at ? " le " + horodate(b.pay_decided_at) : ""));
  if(b.pay_decision_note) morceaux.push("« " + esc(b.pay_decision_note) + " »");
  return morceaux.join("<br>") || "—";
}
function actionsValidation(b){
  const code = (b.validation || {}).code;
  let h = "";
  if(code === "brouillon" && can("paiements.request") && !(b.blocages || []).length)
    h += '<button class="btn small primary" data-demander="' + b.id + '">Demander le règlement</button>';
  if(code === "demande" && can("paiements.approve"))
    h += '<button class="btn small primary" data-decider="' + b.id + '" data-decision="approuve">Approuver</button> ' +
         '<button class="btn small danger" data-decider="' + b.id + '" data-decision="refuse">Refuser</button>';
  if((code === "demande" || code === "refuse") && can("paiements.request"))
    h += ' <button class="btn small" data-annuler="' + b.id + '">Retirer</button>';
  return h || '<span class="muted">—</span>';
}

/* ---------------- pièces jointes ---------------- */
function vuePieces(){
  const fournisseurs = (S.data.fournisseurs || []).filter(f => f.nb_pieces);
  const bons = (S.data.bons || []).filter(b => b.nb_pieces);
  const total = fournisseurs.reduce((s, f) => s + f.nb_pieces, 0) +
                bons.reduce((s, b) => s + b.nb_pieces, 0);
  let h = '<div class="panel"><div class="panel-body" style="color:var(--ink-2)">' +
    "Les pièces se déposent depuis la fiche d'un fournisseur ou d'un bon de commande. " +
    "Formats acceptés : PDF, JPEG, PNG, WEBP, TIFF, 10 Mo au maximum par fichier." +
    "</div></div>";
  if(!total)
    return h + '<div class="panel"><div class="empty"><h4>Aucun document déposé</h4>' +
      "<p>Ouvrez une fiche fournisseur ou un bon de commande pour y joindre un scan.</p></div></div>";

  if(fournisseurs.length){
    h += '<div class="panel"><div class="panel-head"><h3>Dossiers fournisseurs</h3></div>' +
      '<div class="tablewrap"><table><thead><tr><th>Fournisseur</th><th>Dossier</th>' +
      '<th class="num">Pièces</th><th></th></tr></thead><tbody>' +
      fournisseurs.map(f => "<tr><td><strong>" + esc(f.name) + "</strong></td><td>" +
        chip(f.statut_dossier, f.statut_dossier === "Complet" ? "ok" : "warn") +
        '</td><td class="num">' + f.nb_pieces + "</td>" +
        '<td><button class="btn small" data-edit-f="' + f.id + '">Ouvrir la fiche</button></td></tr>').join("") +
      "</tbody></table></div></div>";
  }
  if(bons.length){
    h += '<div class="panel"><div class="panel-head"><h3>Bons de commande</h3></div>' +
      '<div class="tablewrap"><table><thead><tr><th>N° BC</th><th>Fournisseur</th>' +
      '<th class="num">Montant TTC</th><th class="num">Pièces</th><th></th></tr></thead><tbody>' +
      bons.map(b => "<tr><td><strong>" + esc(b.po_number) + "</strong></td><td>" +
        esc(b.supplier_name) + '</td><td class="num">' + montant(b.amount_ttc) +
        '</td><td class="num">' + b.nb_pieces + "</td>" +
        '<td><button class="btn small" data-edit-b="' + b.id + '">Ouvrir le bon</button></td></tr>').join("") +
      "</tbody></table></div></div>";
  }
  return h;
}

/* ---------------- relances ---------------- */
function vueRelances(){
  const d = S.admin.relances;
  if(!d){ api("GET", "/api/relances").then(r => { S.admin.relances = r; render(); })
            .catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }

  let h = "";
  if(!d.messagerie_prete)
    h += '<div class="panel"><div class="panel-body readonly-note" style="margin:0">' +
      "La messagerie n'est pas configurée : renseignez le serveur SMTP et l'adresse " +
      "d'expédition dans Administration → Paramètres, puis définissez la variable " +
      "d'environnement SMTP_PASSWORD sur le serveur." + "</div></div>";

  const aRelancer = (S.data.fournisseurs || []).filter(f => f.statut_dossier !== "Complet");
  if(aRelancer.length){
    h += '<div class="panel"><div class="panel-head"><h3>Fournisseurs à relancer</h3>' +
      '<span class="sub">Dossier incomplet ou C20 à renouveler</span></div>' +
      '<div class="tablewrap"><table><thead><tr><th>Fournisseur</th><th>Adresse</th>' +
      "<th>Motif</th><th>Dernière relance</th><th></th></tr></thead><tbody>" +
      aRelancer.map(f => '<tr class="r-warn"><td><strong>' + esc(f.name) + "</strong></td>" +
        "<td>" + (f.email ? esc(f.email) : '<span class="chip danger">adresse manquante</span>') + "</td>" +
        '<td class="wrapcell">' + esc(f.pieces_manquantes.join(", ")) + "</td>" +
        "<td>" + (f.last_reminder ? dateFr(f.last_reminder) : '<span class="muted">jamais</span>') + "</td>" +
        "<td>" + (can("relances.send") && f.email
          ? '<button class="btn small primary" data-relance-f="' + f.id + '">Relancer</button>'
          : '<button class="btn small" data-edit-f="' + f.id + '">Ouvrir la fiche</button>') +
        "</td></tr>").join("") + "</tbody></table></div></div>";
  }

  const sansFacture = (S.data.bons || []).filter(b =>
    !b.invoice_number || b.invoice_status === "Facture non remise");
  if(sansFacture.length){
    h += '<div class="panel"><div class="panel-head"><h3>Factures originales attendues</h3></div>' +
      '<div class="tablewrap"><table><thead><tr><th>N° BC</th><th>Fournisseur</th>' +
      '<th class="num">Montant TTC</th><th>N° facture</th><th></th></tr></thead><tbody>' +
      sansFacture.map(b => '<tr class="r-warn"><td><strong>' + esc(b.po_number) + "</strong></td>" +
        "<td>" + esc(b.supplier_name) + '</td><td class="num">' + montant(b.amount_ttc) + "</td>" +
        "<td>" + (b.invoice_number ? esc(b.invoice_number) : '<span class="muted">non reçue</span>') + "</td>" +
        "<td>" + (can("relances.send")
          ? '<button class="btn small primary" data-relance-b="' + b.id + '">Relancer</button>'
          : '<span class="muted">—</span>') + "</td></tr>").join("") +
      "</tbody></table></div></div>";
  }

  h += '<div class="panel"><div class="panel-head"><h3>Historique</h3><span class="sub">' +
    d.relances.length + " message(s)</span></div>";
  if(!d.relances.length) h += '<div class="empty"><p>Aucune relance envoyée pour le moment.</p></div></div>';
  else h += '<div class="tablewrap"><table><thead><tr><th>Date</th><th>Sujet</th>' +
    "<th>Destinataire</th><th>Statut</th><th>Envoyé par</th><th>Erreur</th></tr></thead><tbody>" +
    d.relances.map(r => '<tr class="' + (r.statut === "envoye" ? "" : "r-danger") + '">' +
      "<td>" + horodate(r.envoye_le) + "</td><td>" + esc(r.sujet) + "</td>" +
      "<td>" + esc(r.destinataire) + "</td>" +
      "<td>" + chip(r.statut === "envoye" ? "Envoyé" : "Échec", r.statut === "envoye" ? "ok" : "danger") + "</td>" +
      "<td>" + esc(r.envoye_par) + '</td><td class="wrapcell muted">' + esc(r.erreur) + "</td></tr>").join("") +
    "</tbody></table></div></div>";
  return h;
}

/* ---------------- panneau de pièces jointes dans une fiche ---------------- */
const NATURES_PIECES = {
  supplier: [["c20", "C20 / extrait de rôle"], ["rc", "RC / agrément"], ["rib", "RIB"],
             ["autre", "Autre document"]],
  order: [["bon", "Bon de commande signé"], ["facture", "Facture originale"],
          ["devis", "Devis comparatif"], ["paiement", "Justificatif de règlement"],
          ["autre", "Autre document"]],
};
function zonePiecesHtml(entity, id){
  if(!id || !can("pieces.view")) return "";
  return '<fieldset><legend>Pièces jointes</legend>' +
    '<div id="piecesZone" data-entity="' + entity + '" data-id="' + id + '">' +
    '<p class="muted" style="margin:0">Chargement…</p></div></fieldset>';
}
async function chargerPieces(){
  const zone = document.getElementById("piecesZone");
  if(!zone) return;
  const entity = zone.dataset.entity, id = zone.dataset.id;
  let liste = [];
  try { liste = await api("GET", "/api/pieces?entity=" + entity + "&entity_id=" + id); }
  catch(e){ zone.innerHTML = '<p class="formerr">' + esc(e.message) + "</p>"; return; }

  let h = liste.length
    ? '<div class="tablewrap"><table><thead><tr><th>Document</th><th>Nature</th><th>Déposé par</th>' +
      "<th></th></tr></thead><tbody>" +
      liste.map(p => "<tr><td>" + esc(p.filename) +
        '<div class="muted" style="font-size:11.5px">' + Math.round(p.size_bytes / 1024) + " Ko</div></td>" +
        "<td>" + esc(p.nature) + "</td>" +
        "<td>" + esc(p.uploaded_by) + '<div class="muted" style="font-size:11.5px">' +
          horodate(p.uploaded_at) + "</div></td>" +
        '<td><a class="btn small" href="/api/pieces/' + p.id + '">Télécharger</a>' +
        (can("pieces.delete") ? ' <button type="button" class="btn small danger" data-del-piece="' +
          p.id + '">Supprimer</button>' : "") + "</td></tr>").join("") +
      "</tbody></table></div>"
    : '<p class="muted" style="margin:0 0 12px">Aucun document joint.</p>';

  if(can("pieces.upload")){
    const natures = NATURES_PIECES[entity] || NATURES_PIECES.order;
    h += '<div class="devis-grid" style="margin-top:12px">' +
      '<div class="field"><label for="pj-nature">Nature du document</label>' +
      '<select id="pj-nature">' + natures.map(n => '<option value="' + n[0] + '">' + esc(n[1]) + "</option>").join("") +
      "</select></div>" +
      '<div class="field"><label for="pj-fichier">Fichier</label>' +
      '<input type="file" id="pj-fichier" accept=".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff"></div>' +
      '<div class="field"><label>&nbsp;</label>' +
      '<button type="button" class="btn primary" id="pj-envoyer">Déposer</button></div></div>' +
      '<div class="formerr" id="pj-err"></div>';
  }
  zone.innerHTML = h;

  const bouton = document.getElementById("pj-envoyer");
  if(bouton) bouton.addEventListener("click", async () => {
    const champ = document.getElementById("pj-fichier"), err = document.getElementById("pj-err");
    err.textContent = "";
    if(!champ.files.length){ err.textContent = "Choisissez un fichier."; return; }
    const fd = new FormData();
    fd.append("entity", entity); fd.append("entity_id", id);
    fd.append("kind", document.getElementById("pj-nature").value);
    fd.append("fichier", champ.files[0]);
    bouton.disabled = true; bouton.textContent = "Dépôt…";
    try{
      await apiFichier("/api/pieces", fd);
      await chargerPieces();
      toast("Document déposé");
      rafraichirSilencieux();
    } catch(e){
      err.textContent = e.message;
      bouton.disabled = false; bouton.textContent = "Déposer";
    }
  });
}
async function rafraichirSilencieux(){
  try { S.data = await api("GET", "/api/data"); } catch(e){}
}

/* ---------------- administration : utilisateurs ---------------- */
function vueUtilisateurs(){
  const d = S.admin.users;
  if(!d){ api("GET", "/api/admin/users").then(r => { S.admin.users = r; render(); }).catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }
  let h = '<div class="panel"><div class="panel-head"><h3>' + d.utilisateurs.length +
    " comptes</h3><span class=\"sub\">Un compte désactivé ne peut plus se connecter mais reste dans le journal.</span></div>" +
    '<div class="tablewrap"><table><thead><tr><th>Identifiant</th><th>Nom</th><th>Rôle</th>' +
    "<th>État</th><th>Dernière connexion</th><th></th></tr></thead><tbody>";
  for(const u of d.utilisateurs){
    h += '<tr class="' + (u.actif ? "" : "r-warn") + '">' +
      "<td><strong>" + esc(u.username) + "</strong></td>" +
      "<td>" + esc(u.nom) + (u.email ? '<div class="muted" style="font-size:12px">' + esc(u.email) + "</div>" : "") + "</td>" +
      "<td>" + chip(u.role, u.role_code === "ADMIN" ? "primary" : "neutral") + "</td>" +
      "<td>" + chip(u.actif ? "Actif" : "Désactivé", u.actif ? "ok" : "warn") +
        (u.must_change ? " " + chip("mot de passe à changer", "warn") : "") +
        (u.verrouille ? " " + chip("verrouillé", "danger") : "") + "</td>" +
      "<td>" + (u.derniere_connexion ? horodate(u.derniere_connexion) : '<span class="muted">jamais</span>') + "</td>" +
      '<td><button class="btn small" data-edit-u="' + u.id + '">Modifier</button> ' +
      '<button class="btn small" data-reset-u="' + u.id + '">Réinitialiser</button></td></tr>';
  }
  return h + "</tbody></table></div></div>";
}

/* ---------------- administration : rôles ---------------- */
function vueRoles(){
  const d = S.admin.roles;
  if(!d){ api("GET", "/api/admin/roles").then(r => { S.admin.roles = r; render(); }).catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }
  let h = "";
  for(const r of d.roles){
    h += '<div class="panel"><div class="panel-head"><h3>' + esc(r.nom) + "</h3>" +
      '<span class="sub">' + esc(r.code) + " · " + r.nb_utilisateurs + " compte(s) · " +
      r.permissions.length + " permission(s)</span>" +
      '<div class="actions" style="margin-left:auto">' +
      '<button class="btn small" data-edit-r="' + r.id + '">Modifier les permissions</button>' +
      (r.systeme ? "" : ' <button class="btn small danger" data-del-r="' + r.id + '">Supprimer</button>') +
      "</div></div>" +
      '<div class="panel-body"><p style="margin:0 0 10px;color:var(--ink-2)">' + esc(r.description) + "</p>" +
      (r.systeme ? '<p class="muted" style="margin:0 0 10px;font-size:12.5px">Rôle intégré : il conserve toujours l\'ensemble des permissions.</p>' : "") +
      '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
      r.permissions.slice().sort().map(p => chip(p, "neutral")).join(" ") + "</div></div></div>";
  }
  return h;
}

/* ---------------- administration : départements ---------------- */
function vueDepartements(){
  const d = S.admin.departments;
  if(!d){ api("GET", "/api/admin/departments").then(r => { S.admin.departments = r; render(); }).catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }
  let h = '<div class="panel"><div class="tablewrap"><table><thead><tr><th>Département</th>' +
    '<th class="num">Bons de commande</th><th>État</th><th></th></tr></thead><tbody>';
  for(const x of d){
    h += "<tr><td><strong>" + esc(x.nom) + '</strong></td><td class="num">' + x.nb_bons + "</td>" +
      "<td>" + chip(x.actif ? "Actif" : "Inactif", x.actif ? "ok" : "neutral") + "</td>" +
      '<td><button class="btn small" data-edit-d="' + x.id + '">Modifier</button>' +
      (x.nb_bons ? "" : ' <button class="btn small danger" data-del-d="' + x.id + '">Supprimer</button>') +
      "</td></tr>";
  }
  return h + "</tbody></table></div></div>";
}

/* ---------------- administration : journal ---------------- */
function vueJournal(){
  const d = S.admin.audit;
  if(!d){ api("GET", "/api/admin/audit?limite=300").then(r => { S.admin.audit = r; render(); }).catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }
  let h = '<div class="panel"><div class="panel-head"><h3>' + d.length +
    " dernières écritures</h3></div><div class=\"tablewrap\"><table><thead><tr><th>Horodatage</th>" +
    "<th>Utilisateur</th><th>Action</th><th>Objet</th><th>Détail</th><th>Adresse</th></tr></thead><tbody>";
  for(const l of d){
    h += "<tr><td>" + horodate(l.ts) + "</td><td>" + esc(l.username) + "</td><td>" + esc(l.action) +
      "</td><td>" + esc(l.entity) + (l.entity_id ? " #" + esc(l.entity_id) : "") +
      '</td><td class="wrapcell">' + esc(l.details) + '</td><td class="muted">' + esc(l.ip) + "</td></tr>";
  }
  return h + "</tbody></table></div></div>";
}

/* ---------------- administration : paramètres ---------------- */
function vueParametres(){
  const d = S.admin.settings;
  if(!d){ api("GET", "/api/admin/settings").then(r => { S.admin.settings = r; render(); }).catch(e => toast(e.message, true));
    return '<div class="panel"><div class="empty"><p>Chargement…</p></div></div>'; }
  let h = '<div class="panel"><div class="panel-head"><h3>Paramètres généraux</h3>' +
    '<span class="sub">Ces valeurs pilotent directement les contrôles affichés dans les modules.</span></div>' +
    '<div class="panel-body"><form id="form-params"><div class="grid">';
  const champParam = (c) => {
    if(c.type === "booleen")
      return '<div class="field"><div class="checkline"><input type="checkbox" id="p-' + c.cle +
        '" name="' + c.cle + '"' + (String(d.valeurs[c.cle]) === "1" ? " checked" : "") +
        '><label for="p-' + c.cle + '">' + esc(c.libelle) + "</label></div></div>";
    return '<div class="field"><label for="p-' + c.cle + '">' + esc(c.libelle) + "</label>" +
      '<input id="p-' + c.cle + '" name="' + c.cle + '" value="' + esc(d.valeurs[c.cle] || "") + '"' +
      (c.type === "entier" ? ' type="number" min="0" step="1"' : "") + "></div>";
  };
  for(const c of d.champs) h += champParam(c);
  h += '</div><div class="actions" style="margin-top:16px">' +
    '<button type="submit" class="btn primary">Enregistrer les paramètres</button></div>' +
    '<div class="formerr" id="err-params"></div></form></div></div>';

  if(can("admin.mail")){
    h += '<div class="panel"><div class="panel-head"><h3>Messagerie</h3><span class="sub">' +
      (d.messagerie_prete ? "Configurée" : "Non configurée") + "</span></div>" +
      '<div class="panel-body"><form id="form-mail"><div class="grid">' +
      (d.messagerie || []).map(champParam).join("") + "</div>" +
      '<p class="hint" style="margin:12px 0 0">Le mot de passe SMTP ne se saisit pas ici : ' +
      "il est lu dans la variable d'environnement SMTP_PASSWORD du serveur. État actuel : " +
      (d.mot_de_passe_smtp_present ? "défini." : "non défini.") + "</p>" +
      '<div class="actions" style="margin-top:16px">' +
      '<button type="submit" class="btn primary">Enregistrer la messagerie</button>' +
      '<button type="button" class="btn" data-act="test-mail">Envoyer un message de test</button></div>' +
      '<div class="formerr" id="err-mail"></div></form></div></div>';
  }

  h += '<div class="panel"><div class="panel-head"><h3>Données de démonstration</h3></div>' +
    '<div class="panel-body"><p style="margin:0 0 12px;color:var(--ink-2)">' +
    "Charge 6 fournisseurs et 12 bons de commande repris du classeur d'origine. " +
    "Refusé si la base contient déjà des fournisseurs.</p>" +
    '<button class="btn" data-act="demo">Charger le jeu d\'essai</button></div></div>';
  return h;
}

/* ================= formulaires ================= */
function fermerModal(){ $("#modal").innerHTML = ""; }

function modal(titre, corpsHtml, gauche, id, etroit){
  $("#modal").innerHTML =
    '<div class="overlay" data-overlay><div class="sheet' + (etroit ? " narrow" : "") +
    '" role="dialog" aria-modal="true" aria-label="' + esc(titre) + '">' +
      '<div class="sheet-head"><h3>' + esc(titre) + "</h3>" +
      '<button class="btn small" data-act="close">Fermer</button></div>' +
      '<form id="form" data-id="' + esc(id || "") + '"><div class="sheet-body">' + corpsHtml +
      '<div class="formerr" id="formerr"></div></div>' +
      '<div class="sheet-foot"><div>' + (gauche || "") + "</div>" +
      '<div class="actions"><button type="button" class="btn" data-act="close">Fermer</button>' +
      '<button type="submit" class="btn primary" id="submitbtn">Enregistrer</button></div></div></form>' +
    "</div></div>";
  const first = document.querySelector("#form input:not([disabled]), #form select:not([disabled])");
  if(first) first.focus();
}
function champ(name, label, val, type, opt){
  opt = opt || {}; type = type || "text";
  return '<div class="field' + (opt.wide ? " wide" : "") + '"><label for="f-' + name + '">' +
    esc(label) + (opt.req ? " *" : "") + "</label>" +
    '<input id="f-' + name + '" name="' + name + '" type="' + type + '" value="' +
    esc(val == null ? "" : val) + '"' + (type === "number" ? ' step="1" min="0"' : "") +
    (opt.list ? ' list="dl-' + name + '"' : "") + ">" +
    (opt.list ? '<datalist id="dl-' + name + '">' + opt.list.map(o => '<option value="' + esc(o) + '"></option>').join("") + "</datalist>" : "") +
    (opt.hint ? '<span class="hint">' + esc(opt.hint) + "</span>" : "") + "</div>";
}
function selecteur(name, label, val, options, opt){
  opt = opt || {};
  return '<div class="field' + (opt.wide ? " wide" : "") + '"><label for="f-' + name + '">' +
    esc(label) + '</label><select id="f-' + name + '" name="' + name + '"><option value="">—</option>' +
    options.map(o => {
      const v = typeof o === "object" ? o.valeur : o, t = typeof o === "object" ? o.libelle : o;
      return '<option value="' + esc(v) + '"' + (String(val) === String(v) ? " selected" : "") + ">" + esc(t) + "</option>";
    }).join("") + "</select>" + (opt.hint ? '<span class="hint">' + esc(opt.hint) + "</span>" : "") + "</div>";
}
function valeurs(){
  const o = {};
  document.querySelectorAll("#form [name]").forEach(el => {
    o[el.name] = el.type === "checkbox" ? el.checked : el.value.trim();
  });
  return o;
}

/* --- fournisseur --- */
function formulaireFournisseur(id){
  const f = id ? S.data.fournisseurs.find(x => x.id === id)
               : {name:"",department:"",nif:"",rc:"",rib:"",c20_provided:false,c20_date:"",
                  contact:"",email:"",last_reminder:"",note:""};
  if(!f) return;
  const ro = !can("fournisseurs.edit");
  const corpsHtml =
    (ro ? '<div class="readonly-note">Lecture seule : votre rôle ne permet pas de modifier un dossier fournisseur.</div>' : "") +
    "<fieldset" + (ro ? " disabled" : "") + "><legend>Identification</legend><div class=\"grid\">" +
      champ("name", "Nom du fournisseur", f.name, "text", {req: true, wide: true}) +
      selecteur("department", "Département", f.department, S.data.departements) +
    "</div></fieldset>" +
    "<fieldset" + (ro ? " disabled" : "") + "><legend>Pièces du dossier fiscal</legend><div class=\"grid\">" +
      champ("nif", "NIF", f.nif) +
      champ("rc", "N° RC / agrément / carte auto-entrepreneur", f.rc) +
      champ("rib", "RIB", f.rib) +
    '</div><div class="grid" style="margin-top:14px">' +
      '<div class="field"><div class="checkline"><input type="checkbox" id="f-c20_provided" name="c20_provided"' +
        (f.c20_provided ? " checked" : "") + '><label for="f-c20_provided">C20 fourni</label></div></div>' +
      champ("c20_date", "Date du C20", f.c20_date, "date",
            {hint: "Valable " + param("c20_validite_mois", "12") + " mois"}) +
      '<div class="field"><label>Expiration calculée</label><div id="c20exp" class="hint" style="padding-top:8px">—</div></div>' +
    "</div></fieldset>" +
    "<fieldset" + (ro ? " disabled" : "") + "><legend>Suivi</legend><div class=\"grid\">" +
      champ("contact", "Contact (nom · téléphone)", f.contact, "text") +
      champ("email", "Adresse de courriel", f.email, "email",
            {hint: "Utilisée pour les relances automatiques"}) +
      champ("last_reminder", "Date de dernière relance", f.last_reminder, "date") +
      champ("note", "Remarque", f.note, "text", {wide: true}) +
    "</div></fieldset>" + zonePiecesHtml("supplier", id);
  let gauche = (id && can("fournisseurs.delete"))
    ? '<button type="button" class="btn danger" data-del-f="' + id + '">Supprimer</button>' : "";
  if(id && can("relances.send") && f.email && f.statut_dossier !== "Complet")
    gauche += ' <button type="button" class="btn" data-relance-f="' + id + '">Relancer par courriel</button>';
  modal(id ? "Fiche fournisseur" : "Nouveau fournisseur", corpsHtml, gauche, id);
  chargerPieces();
  $("#form").dataset.kind = "fournisseur";
  if(ro) $("#submitbtn").remove();
  majExpiration();
  ["f-c20_date", "f-c20_provided"].forEach(i => {
    const el = document.getElementById(i);
    if(el) el.addEventListener("change", majExpiration);
  });
}
function majExpiration(){
  const el = document.getElementById("c20exp");
  if(!el) return;
  const fourni = (document.getElementById("f-c20_provided") || {}).checked;
  const d = (document.getElementById("f-c20_date") || {}).value;
  if(!fourni || !d){ el.innerHTML = chip("C20 absent", "danger"); return; }
  const mois = parseInt(param("c20_validite_mois", "12"), 10);
  const preavis = parseInt(param("c20_preavis_jours", "60"), 10);
  const base = new Date(d + "T00:00:00");
  const exp = new Date(base); exp.setMonth(exp.getMonth() + mois);
  if(exp.getDate() !== base.getDate()) exp.setDate(0);
  const jours = Math.round((exp - new Date(aujourdhui() + "T00:00:00")) / 86400000);
  const etat = jours < 0 ? ["C20 expiré", "danger"]
             : jours <= preavis ? ["Expire dans " + jours + " j", "warn"] : ["C20 valide", "ok"];
  el.innerHTML = dateFr(exp.toISOString().slice(0, 10)) + " &nbsp; " + chip(etat[0], etat[1]);
}

/* --- bon de commande --- */
function formulaireBon(id){
  const b = id ? S.data.bons.find(x => x.id === id)
               : {po_date: aujourdhui(), po_number:"", department:"", supplier_name:"", description:"",
                  amount_ttc:"", invoice_number:"", invoice_date:"", invoice_status:"",
                  payment_mode:"", cheque_number:"", transfer_number:"", payment_date:"", debit_date:"",
                  quote_done:false, quote_date:"", quote_signed:false, note:""};
  if(!b) return;
  const noms = S.data.fournisseurs.map(f => f.name);
  const roBase = !can("bons.edit"), roFac = !can("factures.edit"), roPay = !can("paiements.edit");
  const seuil = Number(param("seuil_devis", 350000));

  const corpsHtml = bandeauValidation(b) +
    (!can("bons.edit") && !can("factures.edit") && !can("paiements.edit") && !can("devis.edit")
      ? '<div class="readonly-note">Lecture seule.</div>'
      : (roBase || roFac || roPay ? '<div class="readonly-note">Les sections grisées ne relèvent pas de votre rôle.</div>' : "")) +
    "<fieldset" + (roBase ? " disabled" : "") + "><legend>Bon de commande</legend><div class=\"grid\">" +
      champ("po_date", "Date du bon de commande", b.po_date, "date",
            {req: true, hint: "Détermine le mois de rattachement"}) +
      champ("po_number", "N° du bon de commande", b.po_number, "text", {req: true}) +
      selecteur("department", "Département émetteur", b.department, S.data.departements) +
      champ("supplier_name", "Fournisseur", b.supplier_name, "text",
            {req: true, list: noms, hint: "Un nom absent des dossiers fiscaux sera signalé comme non référencé."}) +
      champ("description", "Nature de la prestation", b.description, "text", {wide: true}) +
      champ("amount_ttc", "Montant TTC (" + devise() + ")", b.amount_ttc, "number",
            {req: true, hint: "Devis comparatif obligatoire à partir de " + montant(seuil)}) +
      champ("note", "Remarque", b.note, "text", {wide: true}) +
    '</div></fieldset><div id="devisZone"></div>' +
    "<fieldset" + (roFac ? " disabled" : "") + "><legend>Facture</legend><div class=\"grid\">" +
      champ("invoice_number", "N° de facture", b.invoice_number) +
      champ("invoice_date", "Date de la facture", b.invoice_date, "date") +
      selecteur("invoice_status", "État de la facture", b.invoice_status, S.data.etats_facture) +
    "</div></fieldset>" +
    "<fieldset" + (roPay ? " disabled" : "") + "><legend>Paiement</legend><div class=\"grid\">" +
      selecteur("payment_mode", "Mode de paiement", b.payment_mode, S.data.modes_paiement) +
      champ("cheque_number", "N° de chèque", b.cheque_number) +
      champ("transfer_number", "N° d'ordre de virement", b.transfer_number) +
      champ("payment_date", "Date du paiement", b.payment_date, "date") +
      champ("debit_date", "Date de débit", b.debit_date, "date",
            {hint: "Le statut se déduit de ces deux dates"}) +
    "</div></fieldset>" + zonePiecesHtml("order", id);

  const gauche = (id && can("bons.delete"))
    ? '<button type="button" class="btn danger" data-del-b="' + id + '">Supprimer</button>' : "";
  modal(id ? "Bon de commande " + b.po_number : "Nouveau bon de commande", corpsHtml, gauche, id);
  $("#form").dataset.kind = "bon";
  chargerPieces();
  S.devisForm = {quote_done: !!b.quote_done, quote_date: b.quote_date || "", quote_signed: !!b.quote_signed};
  if(roBase && roFac && roPay && !can("devis.edit")) $("#submitbtn").remove();
  majZoneDevis();
  const mt = document.getElementById("f-amount_ttc");
  if(mt) mt.addEventListener("input", majZoneDevis);
}
function majZoneDevis(){
  const zone = document.getElementById("devisZone");
  if(!zone) return;
  const seuil = Number(param("seuil_devis", 350000));
  const mt = Number((document.getElementById("f-amount_ttc") || {}).value || 0);
  if(mt < seuil){ zone.innerHTML = ""; return; }
  const d = S.devisForm || {};
  const ro = !can("devis.edit");
  zone.innerHTML = '<div class="devis-alert"><h4>Devis comparatif obligatoire</h4>' +
    "<p>Ce bon de commande atteint " + esc(montant(mt)) + " TTC, soit le seuil de " +
    esc(montant(seuil)) + ". Le dossier doit contenir un devis comparatif daté et signé.</p>" +
    '<div class="devis-grid">' +
      '<div class="checkline"><input type="checkbox" id="dv-fait"' + (d.quote_done ? " checked" : "") +
        (ro ? " disabled" : "") + '><label for="dv-fait">Devis comparatif réalisé</label></div>' +
      '<div class="field"><label for="dv-date">Date de création</label>' +
        '<input type="date" id="dv-date" value="' + esc(d.quote_date || "") + '"' + (ro ? " disabled" : "") + "></div>" +
      '<div class="checkline"><input type="checkbox" id="dv-signe"' + (d.quote_signed ? " checked" : "") +
        (ro ? " disabled" : "") + '><label for="dv-signe">Devis comparatif signé</label></div>' +
    "</div></div>";
  const lier = (el, cle, prop) => { if(el) el.addEventListener("change", () => {
    S.devisForm[cle] = prop === "checked" ? el.checked : el.value; }); };
  lier(document.getElementById("dv-fait"), "quote_done", "checked");
  lier(document.getElementById("dv-date"), "quote_date", "value");
  lier(document.getElementById("dv-signe"), "quote_signed", "checked");
}

function bandeauValidation(b){
  if(!b.id || String(param("validation_paiement", "1")) !== "1") return "";
  const v = b.validation || {}, bloc = b.blocages || [];
  let corps = '<div class="devis-alert" style="border-color:var(--' +
    (v.tone === "ok" ? "ok" : v.tone === "danger" ? "danger" : "primary") +
    ');background:var(--surface-2);margin:0 0 20px"><h4 style="color:var(--ink)">' +
    esc(v.label) + "</h4><p>" + suiviValidation(b) + "</p>";
  if(bloc.length)
    corps += '<p style="margin:0 0 10px">' + bloc.map(m => chip(m, "danger")).join(" ") + "</p>";
  const actions = actionsValidation(b);
  if(actions.indexOf("button") !== -1) corps += '<div class="actions">' + actions + "</div>";
  return corps + "</div>";
}

/* --- utilisateur --- */
function formulaireUtilisateur(id){
  const d = S.admin.users;
  const u = id ? d.utilisateurs.find(x => x.id === id) : null;
  const corpsHtml = '<div class="grid">' +
    (u ? '<div class="field"><label>Identifiant</label><input value="' + esc(u.username) + '" disabled></div>'
       : champ("username", "Identifiant de connexion", "", "text", {req: true})) +
    champ("nom", "Nom et prénom", u ? u.nom : "") +
    champ("email", "Adresse e-mail", u ? u.email : "", "email") +
    selecteur("role_id", "Rôle", u ? u.role_id : "", d.roles.map(r => ({valeur: r.id, libelle: r.name}))) +
    '<div class="field"><div class="checkline"><input type="checkbox" id="f-actif" name="actif"' +
      (!u || u.actif ? " checked" : "") + '><label for="f-actif">Compte actif</label></div></div>' +
    (u ? "" : champ("password", "Mot de passe initial (facultatif)", "", "text",
                    {wide: true, hint: "Laissé vide, un mot de passe provisoire est généré."})) +
    "</div>";
  modal(u ? "Modifier " + u.username : "Créer un compte", corpsHtml, "", id || "", true);
  $("#form").dataset.kind = "utilisateur";
}

/* --- rôle --- */
function formulaireRole(id){
  const d = S.admin.roles;
  const r = id ? d.roles.find(x => x.id === id) : {nom:"", code:"", description:"", permissions:[], systeme:false};
  if(!r) return;
  let perms = '<div class="permgrid">';
  for(const g of d.catalogue){
    perms += '<div class="permgroup"><h5>' + esc(g.groupe) + "</h5>";
    for(const p of g.permissions){
      perms += '<label><input type="checkbox" name="perm" value="' + p.code + '"' +
        (r.permissions.includes(p.code) ? " checked" : "") + (r.systeme ? " disabled" : "") + "><span>" +
        esc(p.libelle) + '<br><span class="muted" style="font-size:11.5px">' + p.code + "</span></span></label>";
    }
    perms += "</div>";
  }
  perms += "</div>";
  const corpsHtml = '<div class="grid">' +
    (id ? "" : champ("code", "Code du rôle", "", "text", {req: true, hint: "Majuscules, sans espace"})) +
    champ("nom", "Libellé", r.nom, "text", {req: true}) +
    champ("description", "Description", r.description, "text", {wide: true}) +
    "</div>" +
    (r.systeme ? '<p class="readonly-note">Le rôle administrateur conserve toujours toutes les permissions.</p>' : "") +
    '<fieldset style="margin-top:16px"><legend>Permissions</legend>' + perms + "</fieldset>";
  modal(id ? "Rôle " + r.nom : "Nouveau rôle", corpsHtml, "", id || "");
  $("#form").dataset.kind = "role";
}

/* --- département --- */
function formulaireDepartement(id){
  const x = id ? S.admin.departments.find(d => d.id === id) : {nom: "", actif: true};
  if(!x) return;
  const corpsHtml = '<div class="grid">' + champ("nom", "Nom du département", x.nom, "text", {req: true, wide: true}) +
    '<div class="field"><div class="checkline"><input type="checkbox" id="f-actif" name="actif"' +
    (x.actif ? " checked" : "") + '><label for="f-actif">Proposé à la saisie</label></div></div></div>';
  modal(id ? "Modifier le département" : "Nouveau département", corpsHtml, "", id || "", true);
  $("#form").dataset.kind = "departement";
}

/* --- mot de passe --- */
function formulaireMotDePasse(obligatoire){
  const corpsHtml = (obligatoire
      ? '<p class="readonly-note">Votre mot de passe est provisoire : choisissez-en un nouveau pour continuer.</p>'
      : "") +
    '<div class="grid">' +
    champ("ancien", "Mot de passe actuel", "", "password", {wide: true}) +
    champ("nouveau", "Nouveau mot de passe", "", "password", {wide: true, hint: "10 caractères minimum, lettres et chiffres"}) +
    champ("confirmation", "Confirmation", "", "password", {wide: true}) +
    "</div>";
  modal("Changer de mot de passe", corpsHtml, "", "", true);
  $("#form").dataset.kind = "motdepasse";
}

/* ---------------- connexion ---------------- */
function renderLogin(msg){
  document.getElementById("racine").innerHTML =
    '<div class="login"><div class="login-card">' +
      "<h1>Gestion des fournisseurs</h1>" +
      '<p class="sub">Dossiers fiscaux, bons de commande, factures et paiements</p>' +
      '<form id="loginform">' +
        '<div class="field"><label for="l-user">Identifiant</label>' +
        '<input id="l-user" name="username" autocomplete="username" autofocus></div>' +
        '<div class="field"><label for="l-pass">Mot de passe</label>' +
        '<input id="l-pass" name="password" type="password" autocomplete="current-password"></div>' +
        '<button class="btn primary" type="submit">Se connecter</button>' +
        '<div class="formerr" id="loginerr">' + esc(msg || "") + "</div>" +
      "</form>" +
      '<div class="login-foot">Version ' + esc(window.APP_VERSION || "") + "</div>" +
    "</div></div>";
}

/* ================= événements ================= */
document.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;

  if(form.id === "loginform"){
    const err = $("#loginerr");
    err.textContent = "";
    try{
      const r = await api("POST", "/api/auth/login", {
        username: form.username.value.trim(), password: form.password.value,
      });
      S.session = Object.assign({authenticated: true}, r);
      S.module = (r.modules[0] || {}).code || "tableau";
      await rafraichir();
    } catch(e){ err.textContent = e.message; }
    return;
  }

  if(form.id === "form-mail"){
    const err = $("#err-mail");
    err.textContent = "";
    const body = {};
    form.querySelectorAll("[name]").forEach(el => {
      body[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value.trim();
    });
    try{
      const r = await api("PUT", "/api/admin/settings", body);
      S.session.parametres = r.valeurs;
      S.admin.settings = null; S.admin.relances = null;
      render(); toast("Messagerie enregistrée");
    } catch(e){ err.textContent = e.message; }
    return;
  }

  if(form.id === "form-params"){
    const err = $("#err-params");
    err.textContent = "";
    const body = {};
    form.querySelectorAll("[name]").forEach(el => {
      body[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value.trim();
    });
    try{
      const r = await api("PUT", "/api/admin/settings", body);
      S.session.parametres = r.valeurs;
      S.admin.settings = null;
      await rafraichir();
      toast("Paramètres enregistrés");
    } catch(e){ err.textContent = e.message; }
    return;
  }

  if(form.id !== "form") return;
  const kind = form.dataset.kind, id = form.dataset.id, v = valeurs(), err = $("#formerr");
  err.textContent = "";
  try{
    if(kind === "fournisseur"){
      const body = {name: v.name, department: v.department, nif: v.nif, rc: v.rc, rib: v.rib,
                    c20_provided: v.c20_provided, c20_date: v.c20_date, contact: v.contact,
                    email: v.email, last_reminder: v.last_reminder, note: v.note};
      if(id) await api("PUT", "/api/suppliers/" + id, body);
      else await api("POST", "/api/suppliers", body);
      fermerModal(); await rafraichir(); toast("Fournisseur enregistré");
    }
    else if(kind === "bon"){
      const d = S.devisForm || {};
      const body = {po_date: v.po_date, po_number: v.po_number, department: v.department,
        supplier_name: v.supplier_name, description: v.description, amount_ttc: v.amount_ttc,
        invoice_number: v.invoice_number, invoice_date: v.invoice_date, invoice_status: v.invoice_status,
        payment_mode: v.payment_mode, cheque_number: v.cheque_number, transfer_number: v.transfer_number,
        payment_date: v.payment_date, debit_date: v.debit_date, note: v.note,
        quote_done: d.quote_done, quote_date: d.quote_date, quote_signed: d.quote_signed};
      if(id) await api("PUT", "/api/orders/" + id, body);
      else await api("POST", "/api/orders", body);
      fermerModal(); await rafraichir(); toast("Bon de commande enregistré");
    }
    else if(kind === "utilisateur"){
      if(id){
        await api("PUT", "/api/admin/users/" + id,
                  {nom: v.nom, email: v.email, role_id: Number(v.role_id), actif: v.actif});
        toast("Compte mis à jour");
      } else {
        const r = await api("POST", "/api/admin/users",
                            {username: v.username, nom: v.nom, email: v.email,
                             role_id: Number(v.role_id), actif: v.actif, password: v.password || null});
        toast("Compte créé — mot de passe provisoire : " + r.mot_de_passe_provisoire);
      }
      S.admin.users = null; fermerModal(); render();
    }
    else if(kind === "role"){
      const perms = Array.from(document.querySelectorAll('#form input[name="perm"]:checked')).map(x => x.value);
      if(id) await api("PUT", "/api/admin/roles/" + id, {nom: v.nom, description: v.description, permissions: perms});
      else await api("POST", "/api/admin/roles", {code: v.code, nom: v.nom, description: v.description, permissions: perms});
      S.admin.roles = null; S.admin.users = null; fermerModal();
      S.session = Object.assign(S.session, await api("GET", "/api/auth/session"));
      render(); toast("Rôle enregistré");
    }
    else if(kind === "departement"){
      if(id) await api("PUT", "/api/admin/departments/" + id, {nom: v.nom, actif: v.actif});
      else await api("POST", "/api/admin/departments", {nom: v.nom});
      S.admin.departments = null; fermerModal(); await rafraichir(); toast("Département enregistré");
    }
    else if(kind === "motdepasse"){
      if(v.nouveau !== v.confirmation){ err.textContent = "La confirmation ne correspond pas."; return; }
      await api("POST", "/api/auth/password", {ancien: v.ancien, nouveau: v.nouveau});
      S.session.utilisateur.must_change = false;
      fermerModal(); toast("Mot de passe modifié");
    }
  } catch(e){ err.textContent = e.message; }
});

document.addEventListener("click", async (ev) => {
  if(ev.target.hasAttribute && ev.target.hasAttribute("data-overlay")){ fermerModal(); return; }
  const t = ev.target.closest("[data-mod],[data-act],[data-edit-f],[data-edit-b],[data-edit-u]," +
                              "[data-reset-u],[data-edit-r],[data-del-r],[data-edit-d],[data-del-d]," +
                              "[data-del-f],[data-del-b],[data-valider],[data-demander],[data-decider]," +
                              "[data-annuler],[data-del-piece],[data-relance-f],[data-relance-b]");
  if(!t) return;
  const attr = (n) => t.getAttribute(n);

  if(attr("data-mod")){ S.module = attr("data-mod"); fermerModal(); render(); window.scrollTo({top: 0}); return; }
  if(attr("data-edit-f")){ formulaireFournisseur(Number(attr("data-edit-f"))); return; }
  if(attr("data-edit-b")){ formulaireBon(Number(attr("data-edit-b"))); return; }
  if(attr("data-edit-u")){ formulaireUtilisateur(Number(attr("data-edit-u"))); return; }
  if(attr("data-edit-r")){ formulaireRole(Number(attr("data-edit-r"))); return; }
  if(attr("data-edit-d")){ formulaireDepartement(Number(attr("data-edit-d"))); return; }

  try{
    if(attr("data-reset-u")){
      if(!confirm("Générer un nouveau mot de passe provisoire pour ce compte ?")) return;
      const r = await api("POST", "/api/admin/users/" + attr("data-reset-u") + "/password", {});
      S.admin.users = null; render();
      alert("Nouveau mot de passe provisoire :\n\n" + r.mot_de_passe_provisoire +
            "\n\nÀ transmettre à l'utilisateur ; il devra le changer à la connexion.");
      return;
    }
    if(attr("data-del-r")){
      if(!confirm("Supprimer ce rôle ?")) return;
      await api("DELETE", "/api/admin/roles/" + attr("data-del-r"));
      S.admin.roles = null; render(); toast("Rôle supprimé"); return;
    }
    if(attr("data-del-d")){
      if(!confirm("Supprimer ce département ?")) return;
      await api("DELETE", "/api/admin/departments/" + attr("data-del-d"));
      S.admin.departments = null; render(); toast("Département supprimé"); return;
    }
    if(attr("data-del-f")){
      if(!confirm("Supprimer ce fournisseur ? Les bons de commande le concernant seront signalés comme non référencés.")) return;
      const r = await api("DELETE", "/api/suppliers/" + attr("data-del-f"));
      fermerModal(); await rafraichir();
      toast("Fournisseur supprimé" + (r.bons_orphelins ? " — " + r.bons_orphelins + " bon(s) désormais non référencé(s)" : ""));
      return;
    }
    if(attr("data-del-b")){
      if(!confirm("Supprimer ce bon de commande et son suivi de paiement ?")) return;
      await api("DELETE", "/api/orders/" + attr("data-del-b"));
      fermerModal(); await rafraichir(); toast("Bon de commande supprimé"); return;
    }
    if(attr("data-valider")){
      await api("POST", "/api/orders/" + attr("data-valider") + "/devis/valider", {});
      await rafraichir(); toast("Devis comparatif validé"); return;
    }
    if(attr("data-demander")){
      const r = await api("POST", "/api/orders/" + attr("data-demander") + "/paiement/demander", {});
      fermerModal(); await rafraichir();
      toast(r.approbateurs_notifies
        ? "Demande envoyée — " + r.approbateurs_notifies + " approbateur(s) prévenu(s) par courriel"
        : "Demande de règlement enregistrée");
      return;
    }
    if(attr("data-decider")){
      const decision = attr("data-decision");
      let motif = "";
      if(decision === "refuse"){
        motif = prompt("Motif du refus (obligatoire) :", "") || "";
        if(!motif.trim()) return;
      } else {
        motif = prompt("Observation (facultative) :", "") || "";
      }
      await api("POST", "/api/orders/" + attr("data-decider") + "/paiement/decider",
                {decision: decision, motif: motif});
      fermerModal(); await rafraichir();
      toast(decision === "approuve" ? "Règlement approuvé" : "Demande refusée");
      return;
    }
    if(attr("data-annuler")){
      if(!confirm("Retirer cette demande de règlement ?")) return;
      await api("POST", "/api/orders/" + attr("data-annuler") + "/paiement/annuler", {});
      fermerModal(); await rafraichir(); toast("Demande retirée"); return;
    }
    if(attr("data-del-piece")){
      if(!confirm("Supprimer définitivement ce document ?")) return;
      await api("DELETE", "/api/pieces/" + attr("data-del-piece"));
      await chargerPieces(); await rafraichirSilencieux(); toast("Document supprimé"); return;
    }
    if(attr("data-relance-f")){
      if(!confirm("Envoyer une relance par courriel à ce fournisseur ?")) return;
      const r = await api("POST", "/api/relances/fournisseur/" + attr("data-relance-f"), {});
      S.admin.relances = null; fermerModal(); await rafraichir();
      toast("Relance envoyée à " + r.destinataire); return;
    }
    if(attr("data-relance-b")){
      if(!confirm("Relancer le fournisseur pour la facture originale ?")) return;
      const r = await api("POST", "/api/relances/facture/" + attr("data-relance-b"), {});
      S.admin.relances = null; await rafraichir();
      toast("Relance envoyée à " + r.destinataire); return;
    }
  } catch(e){ toast(e.message, true); return; }

  const act = attr("data-act");
  if(act === "close"){ fermerModal(); }
  else if(act === "new-f"){ formulaireFournisseur(null); }
  else if(act === "new-b"){ formulaireBon(null); }
  else if(act === "new-u"){ formulaireUtilisateur(null); }
  else if(act === "new-r"){ formulaireRole(null); }
  else if(act === "new-d"){ formulaireDepartement(null); }
  else if(act === "mdp"){ formulaireMotDePasse(false); }
  else if(act === "reset-filtres"){ S.filtres = {mois:"", dept:"", fourn:"", q:""}; render(); }
  else if(act === "logout"){
    try { await api("POST", "/api/auth/logout", {}); } catch(e){}
    S.session = null; S.data = null; S.admin = {}; renderLogin("Vous êtes déconnecté.");
  }
  else if(act === "test-mail"){
    const adresse = prompt("Adresse de destination du message de test :", "");
    if(!adresse) return;
    try{
      const r = await api("POST", "/api/admin/mail/test", {destinataire: adresse});
      S.admin.relances = null;
      toast("Message de test envoyé à " + r.destinataire);
    } catch(e){ toast(e.message, true); }
  }
  else if(act === "demo"){
    try{
      t.disabled = true; t.textContent = "Chargement…";
      await api("POST", "/api/admin/demo", {});
      await rafraichir(); toast("Jeu d'essai chargé");
    } catch(e){ toast(e.message, true); render(); }
  }
});

document.addEventListener("change", async (ev) => {
  const el = ev.target;
  if(el.hasAttribute && el.hasAttribute("data-filtre")){
    S.filtres[el.getAttribute("data-filtre")] = el.value; render(); return;
  }
  if(el.hasAttribute && el.hasAttribute("data-devis")){
    const id = el.getAttribute("data-id");
    const b = S.data.bons.find(x => String(x.id) === String(id));
    if(!b) return;
    const body = {quote_done: b.quote_done, quote_date: b.quote_date, quote_signed: b.quote_signed};
    body[el.getAttribute("data-devis")] = el.type === "checkbox" ? el.checked : el.value;
    try{
      await api("PATCH", "/api/orders/" + id + "/devis", body);
      await rafraichir();
    } catch(e){ toast(e.message, true); await rafraichir(); }
  }
});

document.addEventListener("input", (ev) => {
  const el = ev.target;
  if(el.hasAttribute && el.hasAttribute("data-filtre") && el.type === "search"){
    S.filtres.q = el.value;
    clearTimeout(window.__q);
    window.__q = setTimeout(() => {
      render();
      const s = document.querySelector('input[data-filtre="q"]');
      if(s){ s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    }, 280);
  }
});

document.addEventListener("keydown", (ev) => {
  if(ev.key === "Escape" && !(S.session && S.session.utilisateur && S.session.utilisateur.must_change))
    fermerModal();
});

demarrer();
