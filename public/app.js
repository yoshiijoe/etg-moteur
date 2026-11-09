"use strict";
/* Interface du moteur ETG : JavaScript simple, sans framework. Aucune donnée n'est stockée dans la page. */

const ETF = ["Banques", "Pétrole & gaz", "Défense", "Technologie", "Industrie", "Matières premières", "Santé", "Télécoms",
  "Services publics", "Agroalimentaire"];
const DETENUS_DEFAUT = ["Santé", "Technologie", "Pétrole & gaz", "Agroalimentaire"];
const $ = (id) => document.getElementById(id);

const fPct = (v, d = 2, signe = false) => v == null ? "—" :
  new Intl.NumberFormat("fr-FR", { style: "percent", minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: signe ? "exceptZero" : "auto" }).format(v);
const fNum = (v, d = 3) => v == null ? "—" : new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
const fDate = (iso) => { if (!iso) return "—"; const [a, m, j] = iso.slice(0, 10).split("-"); return `${j}/${m}/${a}`; };
const fHeure = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); };

/* ---------- Réseau ---------- */

class ErreurApi extends Error { constructor(message, statut) { super(message); this.statut = statut; } }

async function api(chemin, options = {}) {
  let reponse;
  try {
    reponse = await fetch(chemin, { credentials: "same-origin", ...options });
  } catch (e) {
    throw new ErreurApi("Le serveur ne répond pas. Vérifier la connexion et réessayer.", 0);
  }
  if (reponse.status === 401 && chemin !== "/api/connexion") { afficherConnexion(); throw new ErreurApi("Connexion requise.", 401); }
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}.`;
    try { message = (await reponse.json()).erreur || message; } catch (e) { /* réponse non JSON */ }
    throw new ErreurApi(message, reponse.status);
  }
  return reponse;
}

const post = (chemin, corps) => api(chemin, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps ?? {}) });

function message(texte, erreur = false) {
  const m = $("message");
  m.textContent = texte;
  m.classList.toggle("erreur", erreur);
}

async function avecChargement(bouton, libelle, tache) {
  const ancien = bouton.textContent;
  bouton.disabled = true; bouton.setAttribute("aria-busy", "true"); bouton.textContent = libelle;
  message("");
  try { return await tache(); }
  catch (e) { if (e.statut !== 401) message(`Échec : ${e.message || String(e)}`, true); return undefined; }
  finally { bouton.disabled = false; bouton.removeAttribute("aria-busy"); bouton.textContent = ancien; }
}

/* ---------- Paramètres ---------- */

function parametres() {
  const f = $("form-parametres");
  const v = (n) => f.elements[n];
  const corps = {
    debut: v("debut").value || undefined, fin: v("fin").value || undefined, univers: v("univers").value,
    court: Number(v("court").value), long: Number(v("long").value), top: Number(v("top").value), tampon: Number(v("tampon").value),
    utiliser_court: v("utiliser_court").checked, filtre: v("filtre").checked,
    detenus: [...document.querySelectorAll("#detenus input:checked")].map((c) => c.value),
  };
  if ($("vendredi").value) corps.vendredi = $("vendredi").value;
  if ($("source-tranches")) corps.source_tranches = $("source-tranches").value;
  return corps;
}

/* ---------- Connexion ---------- */

function afficherConnexion() {
  $("application").hidden = true; $("connexion").hidden = false; $("etat-prix").textContent = "Prix : accès réservé";
  $("motdepasse").focus();
}

$("form-connexion").addEventListener("submit", async (e) => {
  e.preventDefault();
  const bouton = e.submitter; bouton.disabled = true;
  $("message-connexion").textContent = ""; $("message-connexion").classList.remove("erreur");
  try {
    await post("/api/connexion", { motdepasse: $("motdepasse").value });
    $("motdepasse").value = ""; $("connexion").hidden = true;
    await /* ---------- Navigation : #moteur et #portefeuille ---------- */

function afficherPage() {
  const page = location.hash === "#portefeuille" ? "portefeuille" : "moteur";
  $("application").dataset.page = page;
  $("page-moteur").hidden = page !== "moteur";
  $("page-portefeuille").hidden = page !== "portefeuille";
  for (const p of ["moteur", "portefeuille"]) {
    const a = $("nav-" + p);
    if (page === p) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  if (typeof pageAffichee === "function") pageAffichee(page);
  if (page === "moteur") for (const id of ["graphique-valeur", "graphique-perte"]) tracer($(id));
}
window.addEventListener("hashchange", afficherPage);
afficherPage();

demarrer();
  } catch (err) {
    $("message-connexion").textContent = err.message; $("message-connexion").classList.add("erreur");
  } finally { bouton.disabled = false; }
});

/* ---------- État des prix ---------- */

let etatPrix = null;

function afficherEtat(e) {
  etatPrix = e;
  if (!e.disponible) {
    $("etat-prix").textContent = "Prix : aucun · Yahoo · non validés";
    $("pied-source").textContent = "Source des prix : Yahoo Finance. Aucun prix en mémoire.";
    return;
  }
  const source = (e.source || "").startsWith("Yahoo") ? "Yahoo" : e.source;
  $("etat-prix").textContent = `Prix au ${fDate(e.dernier_vendredi)} · ${source} · non validés`;
  $("pied-source").textContent = `Source des prix : ${e.source}. Dernier vendredi ${fDate(e.dernier_vendredi)}, ` +
    `${e.semaines} semaines depuis le ${fDate(e.premier_vendredi)}` + (e.mise_a_jour ? `, mis à jour le ${fHeure(e.mise_a_jour)}.` : ".");
}

async function rafraichirEtat() {
  const e = await (await api("/api/etat")).json();
  afficherEtat(e);
  return e;
}

/* ---------- Décision ---------- */

function dessinerDetenus(noms, coches) {
  const conteneur = $("detenus");
  const actuels = new Set(coches ?? [...conteneur.querySelectorAll("input:checked")].map((c) => c.value));
  conteneur.innerHTML = "";
  for (const n of noms) {
    const label = document.createElement("label");
    const c = document.createElement("input");
    c.type = "checkbox"; c.value = n; c.checked = actuels.has(n);
    c.addEventListener("change", planifierDecision);
    label.append(c, document.createTextNode(n));
    conteneur.append(label);
  }
}

const MARQUE = { acheter: "+", garder: "=", vendre: "−", "—": "" };

function afficherDecision(d) {
  $("th-court").textContent = d.libelle_court; $("th-long").textContent = d.libelle_long;
  $("date-decision").textContent = `Clôture du vendredi ${fDate(d.date)}`;
  const apercu = $("apercu");
  apercu.hidden = !d.apercu;
  if (d.apercu) apercu.textContent = `Aperçu : décision officielle le ${fDate(d.date_officielle)}, avec la clôture de ce jour-là.`;
  const corps = $("table-decision").tBodies[0];
  corps.innerHTML = "";
  for (const l of d.lignes) {
    const tr = document.createElement("tr");
    if (l.retenu) tr.className = "retenu";
    const cellules = [
      [l.rang ?? "—", "num"], [l.etf, ""], [fPct(l.court, 1, true), "num"], [fPct(l.long, 1, true), "num"], [fPct(l.signal, 1, true), "num"],
      [l.detenu ? "oui" : "", ""],
      [`${MARQUE[l.action] ? MARQUE[l.action] + " " : ""}${l.action}`, l.action === "acheter" ? "acheter" : l.action === "vendre" ? "vendre" : l.action === "—" ? "neutre" : ""],
    ];
    for (const [texte, classe] of cellules) { const td = document.createElement("td"); td.textContent = texte; if (classe) td.className = classe; tr.append(td); }
    corps.append(tr);
  }
  const places = d.refuges + d.cash;
  $("resume-refuges").textContent = places
    ? `Places remplacées par le filtre : ${d.refuges} ETF monétaire(s), ${d.cash} en cash. Chaque ligne retenue pèse ${fPct(d.poids, 0)} de la poche moteur.`
    : `Chaque ligne retenue pèse ${fPct(d.poids, 0)} de la poche moteur. Vérifier les cours du jour avant de passer les ordres.`;
  dessinerDetenus(d.etf, d.detenus);
}

let minuteurDecision = null;
function planifierDecision() { clearTimeout(minuteurDecision); minuteurDecision = setTimeout(chargerDecision, 250); }

/* Un paramètre du backtest a changé : on recalcule aussi le backtest affiché, pour que l'écran reste à jour. */
let minuteurBacktest = null;
function planifierBacktest() {
  clearTimeout(minuteurBacktest);
  minuteurBacktest = setTimeout(async () => {
    if ($("resultats").hidden) return;
    try { await lancerBacktest(); }
    catch (e) { if (e.statut !== 401) message(e.message, true); }
  }, 400);
}

async function chargerDecision() {
  try {
    afficherDecision(await (await post("/api/decision", parametres())).json());
  } catch (e) { if (e.statut !== 401) message(e.message, true); }
}

/* ---------- Backtest ---------- */

const MESURES_CLES = [["ann", "Rendement par an", (v) => fPct(v, 2)], ["sharpe", "Sharpe", (v) => fNum(v, 2)],
  ["perte_max", "Perte max", (v) => fPct(v, 2)], ["rotation", "Rotation", (v) => fNum(v, 2)]];

function afficherBacktest(b) {
  $("vide-backtest").hidden = true; $("resultats").hidden = false;
  $("periode").textContent = `Du ${fDate(b.periode.debut)} au ${fDate(b.periode.fin)} · ${b.periode.semaines} semaines · ` +
    `${b.parametres.univers === "10" ? "10 ETF" : "9 ETF"} · signal ${b.parametres.utiliser_court ? b.parametres.court + " + " + b.parametres.long : b.parametres.long} sem. · top ${b.parametres.top}, tampon ${b.parametres.tampon}`;
  const bloc = $("chiffres");
  bloc.innerHTML = "";
  for (const [cle, titre, f] of MESURES_CLES) {
    const div = document.createElement("div"); div.className = "chiffre";
    const ref = b.reference[cle];
    div.innerHTML = `<div class="chiffre-titre"></div><div class="chiffre-valeur"></div><div class="chiffre-ref"></div>`;
    div.children[0].textContent = titre; div.children[1].textContent = f(b.moteur[cle]);
    div.children[2].textContent = ref == null ? "STOXX 600 : sans objet" : `STOXX 600 : ${f(ref)}`;
    bloc.append(div);
  }
  const s = b.series;
  dernierBacktest = b;
  majGraphiqueValeur();
  courbes($("graphique-perte"), s.dates, [{ v: s.perte_parts_egales, c: "egal", n: b.parts_egales.nom }, { v: s.perte_reference, c: "ref", n: "STOXX 600" }, { v: s.perte_moteur, c: "moteur", n: "Moteur" }], (v) => fPct(v, 1), true);
  const th = $("table-variantes").tHead; th.innerHTML = "";
  const tr = document.createElement("tr");
  const colonnes = b.colonnes_mesures;
  for (const [i, t] of ["Variante", ...colonnes.map((c) => c.libelle)].entries()) { const e = document.createElement("th"); e.textContent = t; if (i) e.className = "num"; tr.append(e); }
  th.append(tr);
  const corps = $("table-variantes").tBodies[0]; corps.innerHTML = "";
  for (const v of b.variantes) {
    const ligne = document.createElement("tr");
    if (v.nom.startsWith("STOXX") || v.nom.includes("parts égales")) ligne.className = "reference";
    const nom = document.createElement("td"); nom.textContent = v.nom; ligne.append(nom);
    for (const c of colonnes) {
      const td = document.createElement("td"); td.className = "num";
      const x = v.mesures[c.cle];
      td.textContent = x == null ? "" : c.format === "pct" ? fPct(x, 2) : fNum(x, 3);
      ligne.append(td);
    }
    corps.append(ligne);
  }
}

let modeCourbe = "continu";
let dernierBacktest = null;

function majGraphiqueValeur() {
  if (!dernierBacktest) return;
  const b = dernierBacktest;
  const s = b.series;
  const conteneur = $("graphique-valeur");
  const legende = $("legende-valeur");
  const recap = $("recap-annees");

  $("btn-mode-continu")?.classList.toggle("actif", modeCourbe === "continu");
  $("btn-mode-annees")?.classList.toggle("actif", modeCourbe === "annees");

  if (modeCourbe === "continu") {
    if (recap) recap.hidden = true;
    const nomEgal = b.parts_egales.nom;
    if (legende) legende.innerHTML = `<span class="trait moteur"></span>Moteur <span class="trait ref"></span>STOXX Europe 600 <span class="trait egal"></span><span>${nomEgal}</span>`;
    courbes(conteneur, s.dates, [
      { v: s.parts_egales, c: "egal", n: nomEgal },
      { v: s.reference, c: "ref", n: "STOXX 600" },
      { v: s.moteur, c: "moteur", n: "Moteur" }
    ], (v) => fNum(v, 1), false);
  } else {
    if (recap) recap.hidden = false;
    const parAnnee = {};
    s.dates.forEach((d, i) => {
      const an = d.slice(0, 4);
      if (!parAnnee[an]) parAnnee[an] = [];
      parAnnee[an].push({ d, v: s.moteur[i] });
    });

    const anneesTriees = Object.keys(parAnnee).sort();
    const maxSem = Math.max(...Object.values(parAnnee).map((pts) => pts.length));
    const datesAxe = Array.from({ length: maxSem }, (_, i) => `S${String(i + 1).padStart(2, "0")}`);

    const seriesAnnees = [];
    if (recap) recap.innerHTML = "";

    for (const an of anneesTriees) {
      const pts = parAnnee[an];
      const v0 = pts[0].v;
      const valsNorm = pts.map((p) => (p.v / v0) * 100);
      const perfAn = pts[pts.length - 1].v / v0 - 1;

      let som = 100, ddMax = 0;
      for (const val of valsNorm) {
        if (val > som) som = val;
        const dd = val / som - 1;
        if (dd < ddMax) ddMax = dd;
      }

      const classe = an === "2024" ? "an2024" : an === "2025" ? "an2025" : "an2026";
      seriesAnnees.push({ v: valsNorm, c: classe, n: `Moteur ${an}` });

      if (recap) {
        const carte = document.createElement("div");
        carte.className = "carte-annee";
        carte.innerHTML = `
          <div class="carte-annee-titre"><span>${an}</span><span class="trait ${classe}"></span></div>
          <div class="carte-annee-val">${fPct(perfAn, 2, true)}</div>
          <div class="carte-annee-dd">Perte max : ${fPct(ddMax, 1)} · ${pts.length} sem.</div>
        `;
        recap.append(carte);
      }
    }

    if (legende) {
      legende.innerHTML = anneesTriees.map((an) => {
        const classe = an === "2024" ? "an2024" : an === "2025" ? "an2025" : "an2026";
        return `<span class="trait ${classe}"></span>Année ${an} (base 100)`;
      }).join(" ");
    }

    courbes(conteneur, datesAxe, seriesAnnees, (v) => fNum(v, 1), false);
  }
}

$("btn-mode-continu")?.addEventListener("click", () => {
  modeCourbe = "continu";
  majGraphiqueValeur();
});
$("btn-mode-annees")?.addEventListener("click", () => {
  modeCourbe = "annees";
  majGraphiqueValeur();
});

/* Paramètres du backtest affiché : l'Excel doit toujours correspondre à l'écran. */
let parametresAffiches = null;
const memeParametres = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/* ---------- Tranches de 6 mois ---------- */

const fEcart = (v) => fPct(v, 1, true);

function cellule(ligne, texte, classe) {
  const td = document.createElement("td"); td.textContent = texte; if (classe) td.className = classe; ligne.append(td); return td;
}

function afficherTranches(t) {
  $("vide-tranches").hidden = true; $("tranches").hidden = false;
  const s = t.synthese, prm = t.parametres, ref = t.reference;
  $("titre-graphique-tranches").textContent = `Écart avec ${ref}, tranche par tranche`;
  $("th-tranches-bat").textContent = `Bat ${ref}`; $("th-tranches-ref").textContent = ref;
  const premiere = t.lignes[0], derniere = t.lignes[t.lignes.length - 1];
  $("tranches-info").textContent = `${s.tranches} tranches complètes, de ${premiere.tranche} à ${derniere.tranche} · ${t.source_libelle} · ` +
    `${prm.univers === "10" ? "10 ETF" : "9 ETF"} · signal ${prm.utiliser_court ? prm.court + " + " + prm.long : prm.long} sem. · top ${prm.top}, tampon ${prm.tampon} · filtre ${prm.filtre ? "oui" : "non"}`;
  const tuiles = [
    ["Rendement moyen sur 6 mois", fEcart(s.moteur_moyenne), `${ref} : ${fEcart(s.stoxx_moyenne)}`],
    ["Rendement médian", fEcart(s.moteur_mediane), `${ref} : ${fEcart(s.stoxx_mediane)}`],
    ["Tranches où le moteur fait mieux", fPct(s.part_bat_stoxx, 0), `${Math.round(s.part_bat_stoxx * s.tranches)} sur ${s.tranches}`],
    ["Pire tranche", fEcart(s.pire), `${ref} : ${fEcart(s.stoxx_pire)}`],
  ];
  const bloc = $("tranches-chiffres"); bloc.innerHTML = "";
  for (const [titre, valeur, ref] of tuiles) {
    const div = document.createElement("div"); div.className = "chiffre";
    div.innerHTML = `<div class="chiffre-titre"></div><div class="chiffre-valeur"></div><div class="chiffre-ref"></div>`;
    div.children[0].textContent = titre; div.children[1].textContent = valeur; div.children[2].textContent = ref;
    bloc.append(div);
  }
  barres($("graphique-tranches"), t.lignes.map((l) => l.tranche), t.lignes.map((l) => l.ecart));

  const cv = $("table-tranches-variantes").tBodies[0]; cv.innerHTML = "";
  for (const v of t.variantes) {
    const tr = document.createElement("tr"), x = v.synthese;
    cellule(tr, v.nom);
    for (const [val, f] of [[x.moteur_moyenne, fEcart], [x.moteur_mediane, fEcart], [x.ecart_moyen, fEcart],
      [x.part_bat_stoxx, (y) => fPct(y, 0)], [x.part_bat_parts_egales, (y) => fPct(y, 0)], [x.pire, fEcart]]) cellule(tr, f(val), "num");
    cv.append(tr);
  }
  const cd = $("table-tranches").tBodies[0]; cd.innerHTML = "";
  for (const l of [...t.lignes].reverse()) {
    const tr = document.createElement("tr");
    cellule(tr, l.complete ? l.tranche : `${l.tranche} (incomplète)`);
    cellule(tr, String(l.semaines), "num");
    cellule(tr, fEcart(l.moteur), "num"); cellule(tr, fEcart(l.stoxx), "num");
    cellule(tr, fEcart(l.ecart), "num " + (l.ecart > 0 ? "acheter" : "vendre"));
    cellule(tr, fEcart(l.parts_egales), "num"); cellule(tr, fPct(l.perte_max, 1), "num");
    cellule(tr, (l.depart.join(", ") || "aucun ETF") + (l.refuge_depart ? ` + refuge ${fPct(l.refuge_depart, 0)}` : ""));
    cd.append(tr);
  }
  $("tranches-note").textContent = t.note + " Écart moyen " + fEcart(s.ecart_moyen) + ", médian " + fEcart(s.ecart_median) +
    `, fiabilité t = ${fNum(s.t_ecart, 2)} (un écart est considéré comme solide à partir d'environ 2).`;
}

/* Graphique en bâtons : un bâton par tranche, orange si le moteur fait mieux, gris sinon. */
const batons = new Map();
function barres(conteneur, libelles, valeurs) { batons.set(conteneur, { libelles, valeurs }); tracerBarres(conteneur); }

function tracerBarres(conteneur) {
  const g = batons.get(conteneur);
  if (!g || !conteneur.clientWidth) return;
  const { libelles, valeurs } = g;
  const L = conteneur.clientWidth, H = L < 520 ? 200 : 260, m = { h: 12, b: 24, g: 52, d: 8 };
  const graduations = echelle(Math.min(0, ...valeurs), Math.max(0, ...valeurs), 4);
  const mini = graduations[0], maxi = graduations[graduations.length - 1];
  const y = (v) => m.h + (1 - (v - mini) / (maxi - mini)) * (H - m.h - m.b);
  const pas = (L - m.g - m.d) / valeurs.length, largeur = Math.max(1, pas * 0.7);
  const svg = noeud("svg", { viewBox: `0 0 ${L} ${H}`, width: L, height: H });
  for (const v of graduations) {
    svg.append(noeud("line", { x1: m.g, x2: L - m.d, y1: y(v), y2: y(v), class: v === 0 ? "zero" : "grille" }));
    svg.append(noeud("text", { x: m.g - 8, y: y(v) + 4, "text-anchor": "end", class: "axe" }, fPct(v, 0)));
  }
  valeurs.forEach((v, i) => {
    const x = m.g + i * pas + (pas - largeur) / 2;
    const rect = noeud("rect", { x, y: Math.min(y(v), y(0)), width: largeur, height: Math.max(1, Math.abs(y(v) - y(0))), class: v > 0 ? "baton-plus" : "baton-moins" });
    rect.append(noeud("title", {}, `${libelles[i]} : ${fEcart(v)}`));
    svg.append(rect);
    const an = libelles[i].slice(0, 4);
    if (libelles[i].endsWith("S1") && (an % 2 === 0 || pas > 18)) svg.append(noeud("text", { x: x + largeur / 2, y: H - 6, "text-anchor": "middle", class: "axe" }, an));
  });
  conteneur.querySelector("svg")?.remove();
  conteneur.prepend(svg);
}
window.addEventListener("resize", () => batons.forEach((_, c) => tracerBarres(c)));
$("source-tranches").addEventListener("change", () => chargerTranches(parametres()));

async function chargerTranches(p) {
  try { afficherTranches(await (await post("/api/tranches", p)).json()); }
  catch (e) { if (e.statut !== 401) { $("vide-tranches").hidden = false; $("tranches").hidden = true; $("vide-tranches").textContent = e.message; } }
}

async function lancerBacktest() {
  const p = parametres();
  const [b] = await Promise.all([post("/api/backtest", p).then((r) => r.json()), chargerTranches(p)]);
  afficherBacktest(b);
  parametresAffiches = p;
  message(`Backtest terminé : ${b.periode.semaines} semaines, du ${fDate(b.periode.debut)} au ${fDate(b.periode.fin)}.`);
}

/* ---------- Graphiques SVG ---------- */

const ESPACE = "http://www.w3.org/2000/svg";
const graphiques = new Map();

function noeud(nom, attributs = {}, texte) {
  const n = document.createElementNS(ESPACE, nom);
  for (const [k, v] of Object.entries(attributs)) n.setAttribute(k, v);
  if (texte != null) n.textContent = texte;
  return n;
}

/* Graduations « rondes » (1, 2, 2,5, 5 × 10^k) couvrant [mini, maxi]. */
function echelle(mini, maxi, cibles) {
  const brut = (maxi - mini) / cibles || 1;
  const puissance = 10 ** Math.floor(Math.log10(brut));
  const pas = [1, 2, 2.5, 5, 10].map((k) => k * puissance).find((p) => p >= brut);
  const debut = Math.floor(mini / pas) * pas, fin = Math.ceil(maxi / pas) * pas, sortie = [];
  for (let v = debut; v <= fin + pas / 2; v += pas) sortie.push(Math.abs(v) < pas / 1e6 ? 0 : v);
  return sortie;
}

function courbes(conteneur, dates, series, format, depuisZero) {
  graphiques.set(conteneur, { dates, series, format, depuisZero });
  tracer(conteneur);
}

function tracer(conteneur) {
  const g = graphiques.get(conteneur);
  if (!g || !conteneur.clientWidth) return;
  const { dates, series, format, depuisZero } = g;
  const L = conteneur.clientWidth, H = L < 520 ? 220 : 300, m = { h: 12, b: 24, g: 52, d: 8 };
  const toutes = series.flatMap((s) => s.v.filter((v) => v != null));
  if (!toutes.length) return;
  let mini = Math.min(...toutes), maxi = Math.max(...toutes);
  if (depuisZero) maxi = 0;
  const graduations = echelle(mini, maxi, 4);
  mini = Math.min(mini, graduations[0]); maxi = Math.max(maxi, graduations[graduations.length - 1]);
  const x = (i) => m.g + (i / Math.max(1, dates.length - 1)) * (L - m.g - m.d);
  const y = (v) => m.h + (1 - (v - mini) / (maxi - mini || 1)) * (H - m.h - m.b);
  const svg = noeud("svg", { viewBox: `0 0 ${L} ${H}`, width: L, height: H });
  for (const v of graduations) {
    svg.append(noeud("line", { x1: m.g, x2: L - m.d, y1: y(v), y2: y(v), class: "grille" }));
    svg.append(noeud("text", { x: m.g - 8, y: y(v) + 4, "text-anchor": "end", class: "axe" }, format(v)));
  }
  let derniere = null;
  dates.forEach((d, i) => {
    if (d.startsWith("S")) {
      if (i === 0 || i === 12 || i === 25 || i === 38 || i === dates.length - 1) {
        svg.append(noeud("text", { x: x(i), y: H - 6, "text-anchor": "middle", class: "axe" }, d));
      }
    } else {
      const an = d.slice(0, 4);
      if (an !== derniere) {
        derniere = an;
        if (i > 0 && x(i) < L - 30 && x(i) > m.g + 20) svg.append(noeud("text", { x: x(i), y: H - 6, "text-anchor": "middle", class: "axe" }, an));
      }
    }
  });
  for (const s of series) {
    let chemin = "";
    for (let i = 0; i < s.v.length; i++) {
      const val = s.v[i];
      if (val == null) continue;
      chemin += (chemin ? "L" : "M") + `${x(i).toFixed(1)},${y(val).toFixed(1)}`;
    }
    if (chemin) svg.append(noeud("path", { d: chemin, class: `courbe ${s.c}` }));
  }
  const curseur = noeud("line", { y1: m.h, y2: H - m.b, class: "curseur", visibility: "hidden" });
  svg.append(curseur);
  conteneur.querySelector("svg")?.remove(); conteneur.querySelector(".bulle")?.remove();
  conteneur.prepend(svg);
  const bulle = document.createElement("div"); bulle.className = "bulle"; bulle.hidden = true; conteneur.append(bulle);
  const bouger = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ev.clientX - r.left;
    const i = Math.max(0, Math.min(dates.length - 1, Math.round(((px - m.g) / Math.max(1, L - m.g - m.d)) * (dates.length - 1))));
    curseur.setAttribute("x1", x(i)); curseur.setAttribute("x2", x(i)); curseur.setAttribute("visibility", "visible");
    const pointsAffiches = [...series].reverse().filter((s) => s.v[i] != null);
    if (!pointsAffiches.length) return;
    bulle.hidden = false;
    const labelDate = dates[i].startsWith("S") ? `Semaine ${dates[i].slice(1)}` : fDate(dates[i]);
    bulle.textContent = `${labelDate} · ` + pointsAffiches.map((s) => `${s.n} ${format(s.v[i])}`).join(" · ");
    bulle.style.left = Math.max(0, Math.min(L - bulle.offsetWidth, x(i) - bulle.offsetWidth / 2)) + "px";
  };
  svg.addEventListener("pointermove", bouger);
  svg.addEventListener("pointerleave", () => { curseur.setAttribute("visibility", "hidden"); bulle.hidden = true; });
}

if ("ResizeObserver" in window) {
  const obs = new ResizeObserver((entrees) => entrees.forEach((e) => { const g = graphiques.get(e.target); if (g && Math.abs((g.largeur ?? 0) - e.contentRect.width) > 1) { g.largeur = e.contentRect.width; tracer(e.target); } }));
  obs.observe($("graphique-valeur")); obs.observe($("graphique-perte"));
}

/* ---------- Actions ---------- */

$("b-prix").addEventListener("click", () => avecChargement($("b-prix"), "Mise à jour…", async () => {
  const avant = etatPrix;
  message("Téléchargement depuis Yahoo Finance : comptez 10 à 20 secondes.");
  const e = await (await post("/api/prix")).json();
  afficherEtat(e);
  let texte = `Prix mis à jour le ${fHeure(e.mise_a_jour)} : dernier vendredi ${fDate(e.dernier_vendredi)}`;
  if (avant && avant.disponible) {
    const nouvelles = e.semaines - avant.semaines;
    texte += nouvelles > 0 ? `, ${nouvelles} nouvelle(s) semaine(s).` : ". Aucune nouvelle semaine : les prix étaient déjà à jour.";
  } else texte += ".";
  await chargerDecision();
  if (!$("resultats").hidden) await lancerBacktest();
  if (typeof prixMisAJour === "function") prixMisAJour();
  message(texte);
}));

$("b-backtest").addEventListener("click", () => avecChargement($("b-backtest"), "Calcul…", async () => {
  await lancerBacktest();
  if (!$("resultats").hidden) $("resultats").scrollIntoView({ behavior: "smooth", block: "start" });
}));

$("b-excel").addEventListener("click", () => avecChargement($("b-excel"), "Préparation…", async () => {
  clearTimeout(minuteurBacktest); clearTimeout(minuteurDecision);
  const p = parametres();
  if ($("resultats").hidden || !memeParametres(p, parametresAffiches)) await lancerBacktest();
  await chargerDecision();
  const reponse = await post("/api/excel", p);
  const blob = await reponse.blob();
  const nom = /filename="([^"]+)"/.exec(reponse.headers.get("Content-Disposition") || "")?.[1] || "moteur-etg.xlsx";
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(blob); lien.download = nom;
  document.body.append(lien); lien.click(); lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 10000);
  message(`Excel téléchargé : ${nom}`);
}));

$("b-import").addEventListener("click", () => $("fichier-csv").click());
$("fichier-csv").addEventListener("change", (ev) => {
  const fichier = ev.target.files[0]; ev.target.value = "";
  if (!fichier) return;
  avecChargement($("b-import"), "Import…", async () => {
    const e = await (await api("/api/importer", { method: "POST", headers: { "Content-Type": "text/csv" }, body: await fichier.text() })).json();
    afficherEtat(e);
    await chargerDecision();
    if (!$("resultats").hidden) await lancerBacktest();
    message(`CSV importé : prix au ${fDate(e.dernier_vendredi)}`);
  });
});

for (const id of ["vendredi"]) $(id).addEventListener("change", planifierDecision);
$("form-parametres").addEventListener("change", (ev) => {
  if (ev.target.name === "univers") dessinerDetenus(ev.target.value === "10" ? ETF : ETF.filter((n) => n !== "Défense"));
  planifierDecision();
  planifierBacktest();
});
$("form-parametres").addEventListener("submit", (ev) => ev.preventDefault());

/* ---------- Thème ---------- */

$("theme").addEventListener("click", () => {
  const racine = document.documentElement;
  const sombre = racine.dataset.theme ? racine.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const suivant = sombre ? "light" : "dark";
  racine.dataset.theme = suivant;
  try { localStorage.setItem("etg-theme", suivant); } catch (e) { /* stockage indisponible */ }
});

/* ---------- Démarrage ---------- */

async function demarrer() {
  try {
    const e = await rafraichirEtat();
    $("application").hidden = false;
    dessinerDetenus(ETF, DETENUS_DEFAUT);
    if (!e.disponible) { message("Aucun prix en mémoire. Cliquer sur « Mettre à jour les prix », ou importer un CSV."); return; }
    await chargerDecision();
    await lancerBacktest();
    if (typeof chargerPortefeuille === "function") await chargerPortefeuille();
    if (typeof apresDemarrage === "function") apresDemarrage();
  } catch (err) {
    if (err.statut !== 401) { $("application").hidden = false; message(err.message, true); }
  }
}

/* ---------- Navigation fluide : Moteur et Portefeuille ---------- */

function afficherPage() {
  const hash = location.hash;
  const page = hash === "#portefeuille" ? "portefeuille" : "moteur";
  $("application").dataset.page = page;
  $("page-moteur").hidden = false;
  $("page-portefeuille").hidden = false;
  for (const p of ["moteur", "portefeuille"]) {
    const a = $("nav-" + p);
    if (page === p) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  if (hash === "#portefeuille") {
    $("page-portefeuille")?.scrollIntoView({ behavior: "smooth" });
  } else if (hash === "#moteur") {
    $("page-moteur")?.scrollIntoView({ behavior: "smooth" });
  }
  if (typeof pageAffichee === "function") pageAffichee(page);
  for (const id of ["graphique-valeur", "graphique-perte"]) tracer($(id));
}
window.addEventListener("hashchange", afficherPage);
afficherPage();

demarrer();
