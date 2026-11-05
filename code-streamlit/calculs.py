"""Règles métier du partage de frais. Montants en centimes."""


def valider_depense(libelle, montant_centimes, date, participants, date_debut, date_fin):
    """Retourne la liste des erreurs. Vide si la dépense est valide."""
    erreurs = []
    if not libelle.strip():
        erreurs.append("Le libellé est obligatoire.")
    if montant_centimes <= 0:
        erreurs.append("Le montant doit être positif.")
    if not participants:
        erreurs.append("Au moins un participant est requis.")
    if not date_debut <= date <= date_fin:
        erreurs.append(f"La date doit être entre {date_debut} et {date_fin}.")
    return erreurs


def repartir(montant_centimes, nb_participants):
    """Parts égales au centime. Le centime restant va au premier participant."""
    base, reste = divmod(montant_centimes, nb_participants)
    return [base + (1 if i < reste else 0) for i in range(nb_participants)]


def calculer_soldes(conn, groupe_id):
    """Solde de chaque membre du groupe, en centimes. Leur somme vaut toujours 0."""
    soldes = {
        row["id"]: 0
        for row in conn.execute("SELECT id FROM membres WHERE groupe_id = ?", [groupe_id])
    }
    depenses = conn.execute(
        "SELECT id, montant_centimes, payeur_id FROM depenses WHERE groupe_id = ?",
        [groupe_id],
    ).fetchall()
    for dep in depenses:
        parts = conn.execute(
            "SELECT membre_id FROM participants WHERE depense_id = ? ORDER BY rowid",
            [dep["id"]],
        ).fetchall()
        if not parts:
            continue
        soldes[dep["payeur_id"]] += dep["montant_centimes"]
        for membre, part in zip(parts, repartir(dep["montant_centimes"], len(parts))):
            soldes[membre["membre_id"]] -= part
    return soldes


def valider_nom_membre(nom, noms_existants):
    """Erreurs sur le nom d'un membre. Vide si le nom est valide."""
    erreurs = []
    propre = nom.strip()
    if not propre:
        erreurs.append("Le nom est obligatoire.")
    elif any(propre.casefold() == autre.strip().casefold() for autre in noms_existants):
        erreurs.append(f"« {propre} » est déjà membre du groupe.")
    return erreurs


def stats_membres(conn, groupe_id):
    """Par membre : total payé en centimes, nb de dépenses payées, nb de participations."""
    stats = {
        row["id"]: {"paye": 0, "nb_payees": 0, "nb_participations": 0}
        for row in conn.execute("SELECT id FROM membres WHERE groupe_id = ?", [groupe_id])
    }
    payees = conn.execute(
        """SELECT payeur_id, COUNT(*) AS nb, SUM(montant_centimes) AS total
           FROM depenses WHERE groupe_id = ? GROUP BY payeur_id""",
        [groupe_id],
    )
    for row in payees:
        if row["payeur_id"] in stats:
            stats[row["payeur_id"]]["paye"] = row["total"]
            stats[row["payeur_id"]]["nb_payees"] = row["nb"]
    participations = conn.execute(
        """SELECT p.membre_id, COUNT(*) AS nb
           FROM participants p JOIN depenses d ON p.depense_id = d.id
           WHERE d.groupe_id = ? GROUP BY p.membre_id""",
        [groupe_id],
    )
    for row in participations:
        if row["membre_id"] in stats:
            stats[row["membre_id"]]["nb_participations"] = row["nb"]
    return stats


def raisons_de_ne_pas_supprimer(stat):
    """Ce qui rattache un membre à des dépenses. Vide s'il peut être supprimé."""
    raisons = []
    if stat["nb_payees"]:
        raisons.append(f"{stat['nb_payees']} dépense(s) payée(s)")
    if stat["nb_participations"]:
        raisons.append(f"{stat['nb_participations']} participation(s)")
    return raisons
