// Champ « Méthode » lié au jeu choisi : <input data-methods-game="id du select jeu"
// data-methods-charm="id de la case charme chroma" data-methods-hint="id du texte d'aide">.
// Suggestions = méthodes du jeu (data/methodes.json), aide = taux shiny de la méthode.
(() => {
  const source = document.getElementById("methods-data");
  if (!source) return;
  const table = JSON.parse(source.textContent);
  const key = text => text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");

  document.querySelectorAll("[data-methods-game]").forEach(input => {
    const game = document.getElementById(input.dataset.methodsGame);
    const charm = document.getElementById(input.dataset.methodsCharm);
    const hint = document.getElementById(input.dataset.methodsHint);
    const list = input.list;

    const rows = () => table[game.value] || [];
    const fillList = () => {
      list.replaceChildren(...rows().map(([name, , , , description]) => {
        const option = new Option(name);
        if (description) option.label = description;
        return option;
      }));
    };
    const showOdds = () => {
      if (!hint) return;
      const row = rows().find(r => key(r[0]) === key(input.value));
      if (!row) { hint.textContent = ""; return; }
      const [, rate, charmRate, note] = row;
      const parts = [];
      if (rate === 1) parts.push("Shiny garanti");
      else if (rate) {
        const withCharm = charm?.checked && charmRate;
        parts.push(`Taux : 1/${(withCharm ? charmRate : rate).toLocaleString("fr-FR")}`
          + (withCharm ? " (charme chroma)" : charmRate ? ` · 1/${charmRate.toLocaleString("fr-FR")} avec charme chroma` : ""));
      } else parts.push("Taux variable ou inconnu");
      if (note) parts.push(note);
      hint.textContent = parts.join(" · ");
    };

    game.addEventListener("change", () => { fillList(); showOdds(); });
    input.addEventListener("input", showOdds);
    charm?.addEventListener("change", showOdds);
    fillList();
    showOdds();
  });
})();
