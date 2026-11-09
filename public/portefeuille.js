"use strict";
/* Page Portefeuille : positions, indicateurs, corrélations, remplacement d'une ligne.
   Le simulateur mesure le risque et la diversification. Il ne prévoit aucun cours et ne recommande aucun achat.
   Utilise les fonctions de app.js (api, post, fPct, fNum, fDate, $). */

const TYPES_LIGNE = { action: "Action", etf_actions: "ETF actions", etf_obligations: "ETF obligations", etf_inverse: "ETF inverse (−1x)", etf_monetaire: "ETF monétaire" };
const fSigne = (v, d, pct) => v == null ? "—" : new Intl.NumberFormat("fr-FR", pct ? { style: "percent", minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: "exceptZero" } : { minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: "exceptZero" }).format(v);

let pfCharge = false;       // les positions ont été lues au moins une fois
let pfLignes = [];          // lignes saisies : quantite en titres, cible en %
let pfCash = null;
let pfBrouillon = false;
let pfMode = "cible";
let pfCours = {};
let pfPoids = {};
let pfIndicateurs = null;
let pfCompteur = 0;

const pfMessage = (texte, erreur = false) => { const m = $("pf-message"); m.textContent = texte; m.classList.toggle("erreur", erreur); };
const nombre = (v) => { const x = parseFloat(String(v).replace(",", ".")); return Number.isFinite(x) && x >= 0 ? x : 0; };

function pastille(statut) {
  const s = document.createElement("span");
  s.className = "etat " + (statut === "hors règle" ? "hors" : statut === "attention" ? "attention" : "conforme");
  s.textContent = statut === "information" ? "information" : statut;
  return s;
}

/* ---------- Lecture et écriture ---------- */

function depuisServeur(lignes) {
  return lignes.map((l) => ({ code: l.code, nom: l.nom, poche: l.poche, type: l.type, symbole: l.symbole || "", isin: l.isin || "",
    secteur: l.secteur || "", secteur_verifie: !!l.secteur_verifie, scenario: l.scenario || "", quantite: l.quantite || 0,
    cible: Math.round(l.poids * 10000) / 100, devise: l.devise || "EUR", nouvelle: false }));
}

function corpsPortefeuille() {
  return { lignes: pfLignes.map((l) => ({ code: l.code, nom: l.nom, poche: l.poche, type: l.type, symbole: l.symbole || null, isin: l.isin || null,
    secteur: l.secteur, secteur_verifie: l.secteur_verifie, scenario: l.scenario, poids: Math.min(1, l.cible / 100), quantite: l.type === "cash" ? 0 : l.quantite, devise: l.devise })),
    cash: pfCash };
}

async function chargerPortefeuille() {
  try {
    const v = await (await api("/api/portefeuille")).json();
    appliquerVue(v);
    await recalculer();
  } catch (e) { if (e.statut !== 401) pfMessage(e.message, true); }
}

function appliquerVue(v) {
  pfLignes = depuisServeur(v.lignes);
  pfCash = v.cash;
  pfMode = v.mode;
  pfCours = Object.fromEntries(v.lignes.filter((l) => l.cours_eur != null).map((l) => [l.code, l.cours_eur]));
  pfPoids = Object.fromEntries(v.lignes.map((l) => [l.code, l.poids]));
  pfBrouillon = false; pfCharge = true;
  $("pf-cash").value = pfCash ?? "";
  const quand = v.positions ? `Positions enregistrées le ${fHeure(v.positions.mise_a_jour)}.` : "Aucune position enregistrée : poids cibles de la page Stratégie.";
  const prixPf = v.prix_portefeuille ? ` Prix du portefeuille au ${fDate(v.prix_portefeuille.derniere_date)}, mis à jour le ${fHeure(v.prix_portefeuille.mise_a_jour)}.` : "";
  $("pf-etat").textContent = quand + prixPf;
  const select = $("pf-versions"); select.innerHTML = "";
  for (const ver of v.versions) { const o = document.createElement("option"); o.value = ver.nom; o.textContent = fHeure(ver.mise_a_jour); select.append(o); }
  $("pf-versions-zone").hidden = v.versions.length === 0;
  dessinerPositions();
  remplirRemplacement();
}

/* ---------- Tableau des positions ---------- */

function champ(l, cle, type = "text", options = {}) {
  const i = document.createElement("input");
  i.type = type; i.value = l[cle] ?? "";
  if (options.largeur) i.size = options.largeur;
  if (options.ro) i.readOnly = true;
  if (options.etiquette) i.setAttribute("aria-label", `${options.etiquette} ${l.code}`);
  if (type === "number") { i.min = "0"; i.step = "any"; i.inputMode = "decimal"; }
  i.addEventListener("input", () => {
    l[cle] = type === "number" ? nombre(i.value) : i.value.trim();
    if (cle === "secteur") l.secteur_verifie = true;
    if (cle === "symbole") l.symbole = i.value.trim().toUpperCase();
    modifie();
  });
  return i;
}

function dessinerPositions() {
  const corps = $("table-positions").tBodies[0];
  corps.innerHTML = "";
  for (const l of pfLignes) {
    const tr = document.createElement("tr");
    tr.dataset.code = l.code;
    const cash = l.type === "cash";
    const td = (...enfants) => { const c = document.createElement("td"); c.append(...enfants); tr.append(c); return c; };
    const poche = document.createElement("span"); poche.textContent = l.poche; poche.className = "poche";
    const type = document.createElement("select"); type.setAttribute("aria-label", `Type de ${l.code}`);
    if (!cash) {
      for (const [k, v] of Object.entries(TYPES_LIGNE)) { const o = document.createElement("option"); o.value = k; o.textContent = v; type.append(o); }
      type.value = l.type; type.addEventListener("change", () => { l.type = type.value; modifie(); });
    }
    td(poche, ...(cash ? [] : [document.createElement("br"), type]));
    td(champ(l, "code", "text", { ro: !l.nouvelle, largeur: 8, etiquette: "Code" }));
    td(champ(l, "nom", "text", { largeur: 22, etiquette: "Nom" }));
    td(cash ? "" : champ(l, "symbole", "text", { largeur: 10, etiquette: "Symbole" }));
    td(cash ? "" : champ(l, "isin", "text", { largeur: 13, etiquette: "ISIN" }));
    const sect = td(cash ? "" : champ(l, "secteur", "text", { largeur: 18, etiquette: "Secteur" }));
    if (!cash && l.secteur && !l.secteur_verifie) { const v = document.createElement("span"); v.className = "a-verifier"; v.textContent = " à vérifier"; sect.append(v); }
    if (!cash && !l.secteur) { const v = document.createElement("span"); v.className = "a-verifier"; v.textContent = " à définir"; sect.append(v); }
    const sc = document.createElement("select"); sc.setAttribute("aria-label", `Scénario de ${l.code}`);
    for (const [k, v] of [["", "à définir"], ["A", "A"], ["B", "B"], ["C", "C"]]) { const o = document.createElement("option"); o.value = k; o.textContent = v; sc.append(o); }
    sc.value = l.scenario; sc.addEventListener("change", () => { l.scenario = sc.value; modifie(); });
    td(sc);
    td(cash ? "" : champ(l, "quantite", "number", { largeur: 8, etiquette: "Titres" })).className = "num";
    const cours = td(cash ? "" : (pfCours[l.code] != null ? fNum(pfCours[l.code], 2) : "—")); cours.className = "num"; cours.dataset.col = "cours";
    const poids = td(fPct(pfPoids[l.code], 1)); poids.className = "num"; poids.dataset.col = "poids";
    td(champ(l, "cible", "number", { largeur: 6, etiquette: "Poids cible" })).className = "num";
    const suppr = document.createElement("button"); suppr.type = "button"; suppr.className = "bouton discret"; suppr.textContent = "Retirer";
    suppr.setAttribute("aria-label", `Retirer ${l.code}`);
    suppr.addEventListener("click", () => { pfLignes = pfLignes.filter((x) => x !== l); modifie(true); });
    td(cash ? "" : suppr);
    corps.append(tr);
  }
  const total = pfMode === "positions" ? "" : "";
  $("pf-total").textContent = total;
}

function majPoidsCours() {
  for (const tr of $("table-positions").tBodies[0].rows) {
    const code = tr.dataset.code;
    const p = tr.querySelector('[data-col="poids"]'); if (p) p.textContent = fPct(pfPoids[code], 1);
    const c = tr.querySelector('[data-col="cours"]'); if (c && pfCours[code] != null && !pfLignes.find((l) => l.code === code)?.type?.startsWith("cash")) c.textContent = fNum(pfCours[code], 2);
  }
}

function modifie(redessiner = false) {
  pfBrouillon = true;
  pfMessage("Modifications non enregistrées : les indicateurs ci-dessous portent sur ce brouillon.");
  if (redessiner) { dessinerPositions(); remplirRemplacement(); }
  planifierRecalcul();
}

let pfMinuteur = null;
function planifierRecalcul() { clearTimeout(pfMinuteur); pfMinuteur = setTimeout(recalculer, 600); }

$("pf-cash").addEventListener("input", (e) => { pfCash = e.target.value === "" ? null : nombre(e.target.value); modifie(); });

$("pf-ajouter").addEventListener("click", () => {
  pfCompteur += 1;
  let code = "NOUV" + pfCompteur; while (pfLignes.some((l) => l.code === code)) { pfCompteur += 1; code = "NOUV" + pfCompteur; }
  const iCash = pfLignes.findIndex((l) => l.type === "cash");
  const ligne = { code, nom: "", poche: "Autre", type: "action", symbole: "", isin: "", secteur: "", secteur_verifie: false, scenario: "", quantite: 0, cible: 0, devise: "EUR", nouvelle: true };
  pfLignes.splice(iCash < 0 ? pfLignes.length : iCash, 0, ligne);
  modifie(true);
});

$("pf-annuler").addEventListener("click", async () => { pfMessage(""); await chargerPortefeuille(); });

$("pf-enregistrer").addEventListener("click", () => avecPf($("pf-enregistrer"), "Enregistrement…", async () => {
  const v = await (await post("/api/portefeuille", corpsPortefeuille())).json();
  appliquerVue(v);
  await recalculer();
  pfMessage(v.avertissements_prix?.length ? `Positions enregistrées. À noter : ${v.avertissements_prix.join(" ; ")}` : "Positions enregistrées.");
}));

$("pf-restaurer").addEventListener("click", () => avecPf($("pf-restaurer"), "Restauration…", async () => {
  const v = await (await post("/api/portefeuille/restaurer", { nom: $("pf-versions").value })).json();
  appliquerVue(v); await recalculer(); pfMessage("Version restaurée : elle devient la version actuelle.");
}));

$("pf-moteur").addEventListener("click", () => avecPf($("pf-moteur"), "Alignement…", async () => {
  const s = await (await post("/api/portefeuille/moteur", { portefeuille: corpsPortefeuille() })).json();
  const dejaCours = pfCours;
  pfLignes = depuisServeur(s.lignes); pfCash = s.cash;
  pfCours = dejaCours;
  const c = s.changements_moteur;
  dessinerPositions(); remplirRemplacement();
  pfBrouillon = true; await recalculer();
  pfMessage(`Poche moteur alignée sur la décision du ${fDate(c.date_decision)}${c.apercu ? " (aperçu)" : ""} : ` +
    `${c.entres.length ? "entrent " + c.entres.join(", ") : "aucune entrée"} ; ${c.sortis.length ? "sortent " + c.sortis.join(", ") : "aucune sortie"}. ` +
    "Saisissez les titres puis enregistrez : rien n'est encore enregistré.");
}));

async function avecPf(bouton, libelle, tache) {
  const ancien = bouton.textContent;
  bouton.disabled = true; bouton.setAttribute("aria-busy", "true"); bouton.textContent = libelle; pfMessage("");
  try { await tache(); }
  catch (e) { if (e.statut !== 401) pfMessage(`Échec : ${e.message}`, true); }
  finally { bouton.disabled = false; bouton.removeAttribute("aria-busy"); bouton.textContent = ancien; }
}

/* ---------- Indicateurs et corrélations ---------- */

let pfSequence = 0;
async function recalculer() {
  const n = ++pfSequence;
  const portefeuille = corpsPortefeuille();
  $("ind-erreur").hidden = true; $("cor-erreur").hidden = true;
  const [ind, cor] = await Promise.allSettled([
    post("/api/indicateurs", { portefeuille }).then((r) => r.json()),
    post("/api/correlations", { portefeuille, fenetre: Number($("cor-fenetre").value) }).then((r) => r.json()),
  ]);
  if (n !== pfSequence) return;   // un calcul plus récent est en cours
  if (ind.status === "fulfilled") afficherIndicateurs(ind.value);
  else { pfIndicateurs = null; const e = $("ind-erreur"); e.textContent = ind.reason.message; e.hidden = false; $("ind-chiffres").innerHTML = ""; }
  if (cor.status === "fulfilled") afficherCorrelations(cor.value);
  else { const e = $("cor-erreur"); e.textContent = cor.reason.message; e.hidden = false; $("table-correlations").innerHTML = ""; $("cor-alertes").innerHTML = ""; }
}

function tuile(titre, valeur, note, statut) {
  const d = document.createElement("div"); d.className = "chiffre";
  const t = document.createElement("div"); t.className = "chiffre-titre"; t.textContent = titre;
  const v = document.createElement("div"); v.className = "chiffre-valeur"; v.textContent = valeur;
  const n = document.createElement("div"); n.className = "chiffre-ref"; n.textContent = note || "";
  d.append(t, v, n);
  if (statut) d.append(pastille(statut));
  return d;
}

function statutDe(ind, id) { return ind.controles.find((c) => c.id === id)?.statut; }

function afficherIndicateurs(ind) {
  pfIndicateurs = ind;
  pfPoids = Object.fromEntries(ind.lignes_detail.map((l) => [l.code, l.poids]));
  pfCours = { ...pfCours, ...ind.cours_eur };
  majPoidsCours();
  pfMode = ind.mode;
  $("pf-total").textContent = ind.valeur_totale != null ? `Valeur totale : ${fNum(ind.valeur_totale, 2)} €` : "Poids cibles : aucune quantité saisie.";
  const r = ind.risque;
  $("ind-etat").textContent = `${ind.mode === "positions" ? "Poids actuels (derniers cours)" : "Poids cibles"}${pfBrouillon ? " · brouillon non enregistré" : ""}` +
    (r ? ` · risque estimé sur ${r.semaines} semaines` : "");
  const bloc = $("ind-chiffres"); bloc.innerHTML = "";
  if (ind.risque_erreur) { const e = $("ind-erreur"); e.textContent = ind.risque_erreur; e.hidden = false; }
  const perf = ind.performance;
  bloc.append(
    tuile("Volatilité ex-ante", r ? fPct(r.vol_ex_ante, 2) : "—", r ? `poids actuels, ${r.semaines} dernières semaines` : "historique manquant"),
    tuile("Performance ajustée", perf.disponible && perf.performance_ajustee != null ? fNum(perf.performance_ajustee, 2) : "—",
      perf.disponible ? `performance ${fPct(perf.performance, 2, true)} depuis le ${fDate(perf.depuis)} ÷ volatilité` : perf.raison),
    tuile("HHI, cash exclu", fNum(ind.hhi, 4), "approximation : un ETF compte comme une ligne"),
    tuile("Secteurs", String(ind.secteurs), "lignes sectorielles (ETF larges, obligations, inverse exclus)"),
    tuile("Ratio de diversification", r ? fNum(r.diversification, 2) : "—", "Σ poids × volatilités ÷ volatilité du portefeuille"),
    tuile("Bêta vs STOXX 600", r && r.beta != null ? fNum(r.beta, 2) : "—", "estimé sur les mêmes semaines"),
    tuile("Exposition nette aux actions", fPct(ind.exposition_nette, 1), "actions et ETF actions moins l'ETF inverse"),
    tuile("Ligne la plus lourde", ind.ligne_max ? `${fPct(ind.ligne_max.poids, 1)}` : "—", ind.ligne_max ? `${ind.ligne_max.code} · limite 10 %` : "", statutDe(ind, "ligne")),
    tuile("Lignes au-dessus de 5 %", fPct(ind.somme_grosses, 1), "somme · limite 40 %", statutDe(ind, "grosses")),
    tuile("Cash", fPct(ind.cash, 1), ""),
  );
  scenarios(ind);
  controles(ind);
  contributions(ind);
}

function scenarios(ind) {
  const z = $("ind-scenarios"); z.innerHTML = "";
  for (const k of ["A", "B", "C"]) {
    const v = ind.scenarios[k];
    const ligne = document.createElement("div"); ligne.className = "scenario";
    const nom = document.createElement("span"); nom.className = "scenario-nom"; nom.textContent = `Scénario ${k}`;
    const piste = document.createElement("div"); piste.className = "piste";
    piste.style.setProperty("--v", `${Math.min(100, (v / 0.6) * 100)}%`);
    const fourchette = document.createElement("span"); fourchette.className = "fourchette"; fourchette.setAttribute("aria-hidden", "true");
    fourchette.style.setProperty("--a", `${(0.25 / 0.6) * 100}%`); fourchette.style.setProperty("--b", `${((0.45 - 0.25) / 0.6) * 100}%`);
    const rempli = document.createElement("span"); rempli.className = "rempli";
    piste.append(fourchette, rempli);
    const val = document.createElement("span"); val.className = "num"; val.textContent = fPct(v, 1);
    ligne.append(nom, piste, val, pastille(statutDe(ind, "scenario_" + k)));
    z.append(ligne);
  }
  const note = document.createElement("p"); note.className = "aide";
  note.textContent = "La zone grisée est la fourchette de 25 % à 45 %." + (ind.scenarios[""] > 1e-9 ? ` ${fPct(ind.scenarios[""], 1)} du portefeuille n'a pas de scénario défini et ne compte dans aucun.` : "");
  z.append(note);
}

function controles(ind) {
  const corps = $("table-controles").tBodies[0]; corps.innerHTML = "";
  for (const c of ind.controles) {
    const tr = document.createElement("tr");
    const valeur = typeof c.valeur === "number" ? (["ligne", "grosses", "refuge", "secteur", "total"].includes(c.id) || c.id.startsWith("scenario") ? fPct(c.valeur, 1) : String(c.valeur)) : String(c.valeur);
    for (const t of [c.libelle, valeur, c.seuil]) { const td = document.createElement("td"); td.textContent = t; tr.append(td); }
    tr.children[1].className = "num";
    const etat = document.createElement("td"); etat.append(pastille(c.statut)); tr.append(etat);
    const d = document.createElement("td"); d.textContent = c.detail || ""; d.className = "detail"; tr.append(d);
    corps.append(tr);
  }
}

function contributions(ind) {
  const z = $("ind-contributions"); z.innerHTML = "";
  const liste = ind.risque?.contributions_liste;
  if (!liste) { z.textContent = "Contributions indisponibles : historique manquant."; return; }
  const max = Math.max(...liste.map((x) => x.contribution), 0.0001);
  for (const x of liste) {
    const ligne = document.createElement("div"); ligne.className = "barre-ligne";
    const nom = document.createElement("span"); nom.className = "barre-nom"; nom.textContent = x.code;
    const piste = document.createElement("div"); piste.className = "piste-barre";
    const b = document.createElement("span"); b.style.setProperty("--v", `${Math.max(0, (x.contribution / max) * 100)}%`); piste.append(b);
    const val = document.createElement("span"); val.className = "num barre-valeur";
    val.textContent = `${fPct(x.contribution, 1)} du risque · poids ${fPct(x.poids, 1)} · volatilité ${fPct(x.vol, 1)}`;
    ligne.append(nom, piste, val); z.append(ligne);
  }
}

/* ---------- Corrélations ---------- */

function afficherCorrelations(c) {
  const t = $("table-correlations"); t.innerHTML = "";
  const tete = document.createElement("thead"), tr = document.createElement("tr");
  tr.append(document.createElement("th"));
  for (const code of c.codes) { const th = document.createElement("th"); th.textContent = code; th.className = "num"; tr.append(th); }
  tete.append(tr); t.append(tete);
  const corps = document.createElement("tbody");
  c.codes.forEach((a, i) => {
    const ligne = document.createElement("tr");
    const th = document.createElement("th"); th.textContent = a; th.scope = "row"; ligne.append(th);
    c.codes.forEach((b, j) => {
      const cell = document.createElement("td"); cell.className = "num cellule";
      const v = c.matrice[i][j];
      cell.textContent = i === j ? "" : v.toFixed(2).replace(".", ",");
      cell.style.backgroundColor = i === j ? "transparent" : `rgba(255, 91, 0, ${Math.max(0, Math.min(1, v)) * 0.85})`;
      cell.title = `${a} / ${b} : ${v.toFixed(2)}`;
      ligne.append(cell);
    });
    corps.append(ligne);
  });
  t.append(corps);
  const z = $("cor-alertes"); z.innerHTML = "";
  const titre = document.createElement("p"); titre.className = "info";
  titre.textContent = c.alertes.length ? `Paires au-dessus de ${String(c.seuil).replace(".", ",")} (${c.semaines} semaines) :` :
    `Aucune paire au-dessus de ${String(c.seuil).replace(".", ",")} sur ${c.semaines} semaines.`;
  z.append(titre);
  if (c.alertes.length) {
    const ul = document.createElement("ul"); ul.className = "liste-alertes";
    for (const a of c.alertes) { const li = document.createElement("li"); li.textContent = `${a.a} et ${a.b} : ${fNum(a.correlation, 2)}`; ul.append(li); }
    z.append(ul);
  }
  if (c.exclus.length) { const p = document.createElement("p"); p.className = "aide"; p.textContent = `Lignes écartées faute d'historique : ${c.exclus.join(", ")}.`; z.append(p); }
}

$("cor-fenetre").addEventListener("change", recalculer);

/* ---------- Remplacement d'une ligne ---------- */

let simCandidats = [{ symbole: "", poids: "", secteur: "", scenario: "", type: "" }];

function remplirRemplacement() {
  const s = $("sim-remplace"), avant = s.value;
  s.innerHTML = "";
  for (const l of pfLignes.filter((x) => x.type !== "cash")) {
    const o = document.createElement("option"); o.value = l.code; o.textContent = `${l.code} · ${l.nom || l.symbole}`; s.append(o);
  }
  if ([...s.options].some((o) => o.value === avant)) s.value = avant;
  dessinerCandidats();
}

function dessinerCandidats() {
  const z = $("sim-candidats"); z.innerHTML = "";
  const remplacee = pfLignes.find((l) => l.code === $("sim-remplace").value);
  simCandidats.forEach((c, i) => {
    const f = document.createElement("fieldset"); f.className = "candidat";
    const lg = document.createElement("legend"); lg.textContent = `Candidat ${i + 1}`; f.append(lg);
    const mk = (etiquette, cle, placeholder, type = "text") => {
      const l = document.createElement("label"); l.textContent = etiquette;
      const inp = document.createElement("input"); inp.type = type; inp.value = c[cle]; if (placeholder) inp.placeholder = placeholder;
      if (type === "number") { inp.min = "0"; inp.max = "100"; inp.step = "any"; inp.inputMode = "decimal"; }
      inp.addEventListener("input", () => { c[cle] = cle === "symbole" ? inp.value.trim().toUpperCase() : inp.value.trim(); });
      l.append(inp); return l;
    };
    const type = document.createElement("label"); type.textContent = "Type";
    const sel = document.createElement("select");
    for (const [k, v] of [["", "comme la ligne remplacée"], ...Object.entries(TYPES_LIGNE).filter(([k]) => k !== "etf_monetaire")]) { const o = document.createElement("option"); o.value = k; o.textContent = v; sel.append(o); }
    sel.value = c.type; sel.addEventListener("change", () => { c.type = sel.value; }); type.append(sel);
    const sc = document.createElement("label"); sc.textContent = "Scénario";
    const ss = document.createElement("select");
    for (const [k, v] of [["", "comme la ligne remplacée"], ["A", "A"], ["B", "B"], ["C", "C"]]) { const o = document.createElement("option"); o.value = k; o.textContent = v; ss.append(o); }
    ss.value = c.scenario; ss.addEventListener("change", () => { c.scenario = ss.value; }); sc.append(ss);
    f.append(mk("Symbole Yahoo", "symbole", "ex. SAN.PA"), mk("Poids (%)", "poids", remplacee ? `${(remplacee.cible).toString().replace(".", ",")} (poids actuel de la ligne)` : "", "number"),
      mk("Secteur", "secteur", "à définir"), sc, type);
    if (simCandidats.length > 1) {
      const b = document.createElement("button"); b.type = "button"; b.className = "bouton discret"; b.textContent = "Retirer ce candidat";
      b.addEventListener("click", () => { simCandidats.splice(i, 1); dessinerCandidats(); }); f.append(b);
    }
    z.append(f);
  });
  $("sim-ajouter").disabled = simCandidats.length >= 3;
}

$("sim-remplace").addEventListener("change", dessinerCandidats);
$("sim-ajouter").addEventListener("click", () => { if (simCandidats.length < 3) { simCandidats.push({ symbole: "", poids: "", secteur: "", scenario: "", type: "" }); dessinerCandidats(); } });

$("sim-lancer").addEventListener("click", async () => {
  const bouton = $("sim-lancer"), ancien = bouton.textContent;
  const m = $("sim-message");
  const candidats = simCandidats.filter((c) => c.symbole).map((c) => {
    const o = { symbole: c.symbole, secteur: c.secteur };
    if (c.poids !== "") o.poids = nombre(c.poids) / 100;
    if (c.scenario) o.scenario = c.scenario;
    if (c.type) o.type = c.type;
    return o;
  });
  m.classList.remove("erreur");
  if (!candidats.length) { m.textContent = "Saisir au moins un symbole candidat."; m.classList.add("erreur"); return; }
  bouton.disabled = true; bouton.setAttribute("aria-busy", "true"); bouton.textContent = "Simulation…"; m.textContent = "Téléchargement des candidats depuis Yahoo Finance…";
  try {
    const r = await (await post("/api/simulation", { portefeuille: corpsPortefeuille(), remplace: $("sim-remplace").value, candidats })).json();
    afficherSimulation(r); m.textContent = "";
    simulationAffichee = r;
  } catch (e) { if (e.statut !== 401) { m.textContent = `Échec : ${e.message}`; m.classList.add("erreur"); } }
  finally { bouton.disabled = false; bouton.removeAttribute("aria-busy"); bouton.textContent = ancien; }
});

let simulationAffichee = null;
const LIGNES_ECARTS = [
  ["vol_ex_ante", "Volatilité ex-ante", (v) => fPct(v, 2), (v) => fSigne(v, 2, true)],
  ["diversification", "Ratio de diversification", (v) => fNum(v, 2), (v) => fSigne(v, 2, false)],
  ["beta", "Bêta vs STOXX 600", (v) => fNum(v, 2), (v) => fSigne(v, 2, false)],
  ["hhi", "HHI, cash exclu", (v) => fNum(v, 4), (v) => fSigne(v, 4, false)],
  ["secteurs", "Nombre de secteurs", (v) => String(v), (v) => fSigne(v, 0, false)],
  ["exposition_nette", "Exposition nette aux actions", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
  ["ligne_max", "Ligne la plus lourde", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
  ["somme_grosses", "Lignes au-dessus de 5 %", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
  ["scenario_A", "Scénario A", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
  ["scenario_B", "Scénario B", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
  ["scenario_C", "Scénario C", (v) => fPct(v, 1), (v) => fSigne(v, 1, true)],
];

function valeurAvant(ind, cle) {
  const r = ind.risque || {};
  return { vol_ex_ante: r.vol_ex_ante, diversification: r.diversification, beta: r.beta, hhi: ind.hhi, secteurs: ind.secteurs,
    exposition_nette: ind.exposition_nette, ligne_max: ind.ligne_max?.poids, somme_grosses: ind.somme_grosses,
    scenario_A: ind.scenarios.A, scenario_B: ind.scenarios.B, scenario_C: ind.scenarios.C }[cle];
}

function afficherSimulation(r) {
  const z = $("sim-resultats"); z.innerHTML = "";
  const ok = r.resultats.filter((x) => x.avant);
  const intro = document.createElement("p"); intro.className = "info";
  intro.textContent = `Remplacement de ${r.remplace} (${r.nom_remplace}, poids ${fPct(r.poids_remplace, 1)}).`; z.append(intro);
  for (const x of r.resultats.filter((y) => !y.avant)) {
    const d = document.createElement("div"); d.className = "alerte-candidat";
    const t = document.createElement("strong"); t.textContent = x.symbole + " : "; d.append(t, document.createTextNode(x.erreur));
    if (x.controles_candidat) for (const c of x.controles_candidat) { const p = document.createElement("p"); p.className = "aide"; p.append(pastille(c.statut), document.createTextNode(` ${c.libelle}`)); d.append(p); }
    z.append(d);
  }
  if (!ok.length) return;
  const tw = document.createElement("div"); tw.className = "defile";
  const t = document.createElement("table"); t.className = "simulation";
  const th = document.createElement("thead"), tr = document.createElement("tr");
  for (const [i, h] of ["Indicateur", "Avant", ...ok.flatMap((x) => [`Après : ${x.symbole}`, "Écart"])].entries()) { const e = document.createElement("th"); e.textContent = h; if (i) e.className = "num"; tr.append(e); }
  th.append(tr); t.append(th);
  const tb = document.createElement("tbody");
  for (const [cle, libelle, f, fe] of LIGNES_ECARTS) {
    const ligne = document.createElement("tr");
    const n = document.createElement("td"); n.textContent = libelle; ligne.append(n);
    const a = document.createElement("td"); a.className = "num"; const va = valeurAvant(ok[0].avant, cle); a.textContent = va == null ? "—" : f(va); ligne.append(a);
    for (const x of ok) {
      const ap = document.createElement("td"); ap.className = "num"; const vp = valeurAvant(x.apres, cle); ap.textContent = vp == null ? "—" : f(vp);
      const ec = document.createElement("td"); ec.className = "num ecart"; ec.textContent = x.ecarts[cle] == null ? "—" : fe(x.ecarts[cle]);
      ligne.append(ap, ec);
    }
    tb.append(ligne);
  }
  t.append(tb); tw.append(t); z.append(tw);
  const fen = document.createElement("p"); fen.className = "aide";
  fen.textContent = `Calculé sur les mêmes ${ok[0].semaines} semaines avant et après. ${ok[0].note}`; z.append(fen);
  for (const x of ok) {
    const bloc = document.createElement("div"); bloc.className = "candidat-resultat";
    const h = document.createElement("h2"); h.textContent = `${x.symbole} : volatilité, corrélations et règles`; bloc.append(h);
    const v = document.createElement("p"); v.className = "info"; v.textContent = `Volatilité du candidat : ${fPct(x.candidat_vol, 2)} par an. Poids simulé : ${fPct(x.candidat.poids, 1)}.`; bloc.append(v);
    const ctl = document.createElement("ul"); ctl.className = "liste-controles";
    for (const c of x.controles_candidat) { const li = document.createElement("li"); li.append(pastille(c.statut), document.createTextNode(` ${c.libelle}`)); ctl.append(li); }
    bloc.append(ctl);
    if (x.changements_de_statut.length) {
      const p = document.createElement("p"); p.className = "info"; p.textContent = "Règles dont l'état change : " +
        x.changements_de_statut.map((c) => `${c.libelle} (${c.avant} → ${c.apres})`).join(" ; ") + "."; bloc.append(p);
    }
    const tc = document.createElement("div"); tc.className = "defile";
    const tab = document.createElement("table"); tab.innerHTML = "<thead><tr><th>Corrélation avec</th><th class=\"num\">52 sem.</th><th></th></tr></thead>";
    tab.tHead.rows[0].cells[1].textContent = `${x.semaines} sem.`;
    const tbd = document.createElement("tbody");
    for (const c of x.candidat_correlations) {
      const l = document.createElement("tr");
      const a = document.createElement("td"); a.textContent = c.code;
      const b = document.createElement("td"); b.className = "num"; b.textContent = fNum(c.correlation, 2);
      const d = document.createElement("td"); if (c.correlation > 0.7) d.append(pastille("attention"), document.createTextNode(" au-dessus de 0,7"));
      l.append(a, b, d); tbd.append(l);
    }
    tab.append(tbd); tc.append(tab); bloc.append(tc);
    z.append(bloc);
  }
}

/* ---------- Intégration avec la page principale ---------- */

function pageAffichee(page) {
  if (page === "portefeuille" && !pfCharge && !$("application").hidden) chargerPortefeuille();
  if (page === "portefeuille" && pfCharge && pfIndicateurs) { /* rien à redessiner */ }
}
function apresDemarrage() { if (location.hash === "#portefeuille" && !pfCharge) chargerPortefeuille(); }
function prixMisAJour() { if (pfCharge) chargerPortefeuille(); }
