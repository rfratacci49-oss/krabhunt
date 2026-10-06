// Liste « Forme » liée à un champ Pokémon : <div data-forms-for="id-du-champ"> contenant un <select>.
// Elle n'apparaît que si l'espèce choisie a des formes (régionales, cosmétiques…).
(async () => {
  const pickers = document.querySelectorAll("[data-forms-for]");
  if (!pickers.length) return;

  let forms = {};
  try {
    forms = await (await fetch("/formes.json")).json();
  } catch (e) {
    return; // sans la liste, le formulaire reste utilisable avec la forme de base
  }

  pickers.forEach(picker => {
    const input = document.getElementById(picker.dataset.formsFor);
    const select = picker.querySelector("select");
    // Nom (sans accents ni ponctuation) ou n° -> [n°, nom exact], depuis la datalist du champ (« #25 »)
    const key = text => text.toLowerCase().replace(/♀/g, "f").replace(/♂/g, "m")
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]/g, "");
    const species = {};
    input.list?.querySelectorAll("option").forEach(o => {
      const dex = String(parseInt(o.textContent.replace("#", ""), 10));
      species[key(o.value)] = species[dex] = [dex, o.value];
    });
    const find = () => species[key(input.value.replace(/^\s*#?0*/, ""))] || species[key(input.value)];

    let wanted = select.dataset.selected || "";
    const update = () => {
      const info = forms[find()?.[0]];
      picker.hidden = !info;
      select.replaceChildren();
      if (!info) return;
      select.append(new Option(info.default, ""));
      for (const [key, name] of Object.entries(info.forms)) {
        select.append(new Option(name, key, false, key === wanted));
      }
    };
    select.addEventListener("change", () => { wanted = select.value; });
    input.addEventListener("input", update);
    input.addEventListener("change", () => {
      const match = find();
      if (match) input.value = match[1];  // « 25 » ou « evoli » -> « Pikachu », « Évoli »
      update();
    });
    update();
  });
})();
