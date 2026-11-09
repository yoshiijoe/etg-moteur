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
    await demarrer();
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
  courbes($("graphique-valeur"), s.dates, [{ v: s.reference, c: "ref", n: "STOXX 600" }, { v: s.moteur, c: "moteur", n: "Moteur" }], (v) => fNum(v, 1), false);
  courbes($("graphique-perte"), s.dates, [{ v: s.perte_reference, c: "ref", n: "STOXX 600" }, { v: s.perte_moteur, c: "moteur", n: "Moteur" }], (v) => fPct(v, 1), true);
  const th = $("table-variantes").tHead; th.innerHTML = "";
  const tr = document.createElement("tr");
  const colonnes = b.colonnes_mesures;
  for (const [i, t] of ["Variante", ...colonnes.map((c) => c.libelle)].entries()) { const e = document.createElement("th"); e.textContent = t; if (i) e.className = "num"; tr.append(e); }
  th.append(tr);
  const corps = $("table-variantes").tBodies[0]; corps.innerHTML = "";
  for (const v of b.variantes) {
    const ligne = document.createElement("tr");
    if (v.nom.startsWith("STOXX")) ligne.className = "reference";
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

async function lancerBacktest() {
  const b = await (await post("/api/backtest", parametres())).json();
  afficherBacktest(b);
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
  const toutes = series.flatMap((s) => s.v);
  let mini = Math.min(...toutes), maxi = Math.max(...toutes);
  if (depuisZero) maxi = 0;
  const graduations = echelle(mini, maxi, 4);
  mini = Math.min(mini, graduations[0]); maxi = Math.max(maxi, graduations[graduations.length - 1]);
  const x = (i) => m.g + (i / (dates.length - 1)) * (L - m.g - m.d);
  const y = (v) => m.h + (1 - (v - mini) / (maxi - mini)) * (H - m.h - m.b);
  const svg = noeud("svg", { viewBox: `0 0 ${L} ${H}`, width: L, height: H });
  for (const v of graduations) {
    svg.append(noeud("line", { x1: m.g, x2: L - m.d, y1: y(v), y2: y(v), class: "grille" }));
    svg.append(noeud("text", { x: m.g - 8, y: y(v) + 4, "text-anchor": "end", class: "axe" }, format(v)));
  }
  let derniere = null;
  dates.forEach((d, i) => {
    const an = d.slice(0, 4);
    if (an !== derniere) { derniere = an; if (i > 0 && x(i) < L - 30 && x(i) > m.g + 20) svg.append(noeud("text", { x: x(i), y: H - 6, "text-anchor": "middle", class: "axe" }, an)); }
  });
  for (const s of series) {
    const d = s.v.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    svg.append(noeud("path", { d, class: `courbe ${s.c}` }));
  }
  const curseur = noeud("line", { y1: m.h, y2: H - m.b, class: "curseur", visibility: "hidden" });
  svg.append(curseur);
  conteneur.querySelector("svg")?.remove(); conteneur.querySelector(".bulle")?.remove();
  conteneur.prepend(svg);
  const bulle = document.createElement("div"); bulle.className = "bulle"; bulle.hidden = true; conteneur.append(bulle);
  const bouger = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ev.clientX - r.left;
    const i = Math.max(0, Math.min(dates.length - 1, Math.round(((px - m.g) / (L - m.g - m.d)) * (dates.length - 1))));
    curseur.setAttribute("x1", x(i)); curseur.setAttribute("x2", x(i)); curseur.setAttribute("visibility", "visible");
    bulle.hidden = false;
    bulle.textContent = `${fDate(dates[i])} · ` + [...series].reverse().map((s) => `${s.n} ${format(s.v[i])}`).join(" · ");
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
  message(texte);
}));

$("b-backtest").addEventListener("click", () => avecChargement($("b-backtest"), "Calcul…", async () => {
  await lancerBacktest();
  if (!$("resultats").hidden) $("resultats").scrollIntoView({ behavior: "smooth", block: "start" });
}));

$("b-excel").addEventListener("click", () => avecChargement($("b-excel"), "Préparation…", async () => {
  const reponse = await post("/api/excel", parametres());
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
    message(`CSV importé : prix au ${fDate(e.dernier_vendredi)}`);
    await chargerDecision();
  });
});

for (const id of ["vendredi"]) $(id).addEventListener("change", planifierDecision);
$("form-parametres").addEventListener("change", (ev) => {
  if (ev.target.name === "univers") dessinerDetenus(ev.target.value === "10" ? ETF : ETF.filter((n) => n !== "Défense"));
  planifierDecision();
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
  } catch (err) {
    if (err.statut !== 401) { $("application").hidden = false; message(err.message, true); }
  }
}

demarrer();
