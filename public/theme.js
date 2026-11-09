// Thème appliqué avant l'affichage pour éviter un flash (fichier externe : la CSP interdit les scripts dans la page)
try { var t = localStorage.getItem("etg-theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
