"""
Module de logique métier pour la gestion du partage de frais.
Gère les groupes, les membres, les dépenses et le calcul exact des soldes.
"""

from datetime import date
from typing import Any, Dict, List, Optional


def valider_date_format(valeur: Any) -> str:
    """Convertit et valide une date au format YYYY-MM-DD."""
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        valeur = valeur.strip()
        # Vérification simple du format YYYY-MM-DD
        date.fromisoformat(valeur)
        return valeur
    raise ValueError(f"Format de date invalide : {valeur}")


def formater_date_fr(valeur: Any) -> str:
    """Formate une date au format DD/MM/YYYY."""
    if not valeur:
        return ""
    if isinstance(valeur, str):
        try:
            valeur = date.fromisoformat(valeur.strip())
        except ValueError:
            return valeur
    if isinstance(valeur, date):
        return valeur.strftime("%d/%m/%Y")
    return str(valeur)


def obtenir_groupes(conn) -> List[Dict[str, Any]]:
    """Récupère la liste de tous les groupes."""
    rows = conn.execute("SELECT id, nom, date_debut, date_fin FROM groupes ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


def obtenir_groupe(conn, groupe_id: int) -> Optional[Dict[str, Any]]:
    """Récupère un groupe par son identifiant."""
    row = conn.execute(
        "SELECT id, nom, date_debut, date_fin FROM groupes WHERE id = ?",
        [groupe_id],
    ).fetchone()
    return dict(row) if row else None


def creer_groupe(
    conn,
    nom: str,
    date_debut: Any,
    date_fin: Any,
    noms_membres: Optional[List[str]] = None,
) -> int:
    """
    Crée un groupe avec son nom, ses dates de séjour et ses membres initiaux.
    """
    nom = (nom or "").strip()
    if not nom:
        raise ValueError("Le nom du groupe ne peut pas être vide.")

    debut_str = valider_date_format(date_debut)
    fin_str = valider_date_format(date_fin)
    if debut_str > fin_str:
        raise ValueError(
            f"La date de début ({debut_str}) ne peut pas être postérieure à la date de fin ({fin_str})."
        )

    # Nettoyage des noms de membres
    membres_propres = []
    if noms_membres:
        for m in noms_membres:
            nom_m = m.strip()
            if nom_m and nom_m not in membres_propres:
                membres_propres.append(nom_m)

    cur = conn.execute(
        "INSERT INTO groupes (nom, date_debut, date_fin) VALUES (?, ?, ?)",
        [nom, debut_str, fin_str],
    )
    groupe_id = cur.lastrowid

    for m in membres_propres:
        conn.execute(
            "INSERT INTO membres (groupe_id, nom) VALUES (?, ?)",
            [groupe_id, m],
        )

    conn.commit()
    return groupe_id


def supprimer_groupe(conn, groupe_id: int) -> None:
    """Supprime un groupe et toutes ses données associées (en cascade)."""
    conn.execute("DELETE FROM groupes WHERE id = ?", [groupe_id])
    conn.commit()


def obtenir_membres(conn, groupe_id: int) -> List[Dict[str, Any]]:
    """Récupère tous les membres d'un groupe ordonnés par id."""
    rows = conn.execute(
        "SELECT id, groupe_id, nom FROM membres WHERE groupe_id = ? ORDER BY id ASC",
        [groupe_id],
    ).fetchall()
    return [dict(r) for r in rows]


def ajouter_membre(conn, groupe_id: int, nom: str) -> int:
    """Ajoute un membre à un groupe."""
    nom = (nom or "").strip()
    if not nom:
        raise ValueError("Le nom du membre ne peut pas être vide.")

    # Vérification de l'existence du groupe
    if not obtenir_groupe(conn, groupe_id):
        raise ValueError(f"Le groupe {groupe_id} n'existe pas.")

    # Vérification d'unicité du nom dans le groupe
    existant = conn.execute(
        "SELECT id FROM membres WHERE groupe_id = ? AND LOWER(nom) = LOWER(?)",
        [groupe_id, nom],
    ).fetchone()
    if existant:
        raise ValueError(f"Un membre nommé '{nom}' existe déjà dans ce groupe.")

    cur = conn.execute(
        "INSERT INTO membres (groupe_id, nom) VALUES (?, ?)",
        [groupe_id, nom],
    )
    conn.commit()
    return cur.lastrowid


def calculer_parts_depense(montant_centimes: int, participant_ids: List[int]) -> List[Dict[str, int]]:
    """
    Calcule la part due par chaque participant pour une dépense :
    - Dépense partagée à parts égales entre les participants.
    - Le centime restant va au premier participant ajouté.
    - La somme des parts est exactement égale au montant de la dépense.
    """
    if not participant_ids:
        raise ValueError("Une dépense doit avoir au moins un participant.")
    if montant_centimes <= 0:
        raise ValueError("Le montant de la dépense doit être strictement positif.")

    k = len(participant_ids)
    part_base = montant_centimes // k
    reste = montant_centimes % k

    repartition = []
    for idx, pid in enumerate(participant_ids):
        # Le premier participant ajouté (idx == 0) reçoit le ou les centimes restants
        part = part_base + (reste if idx == 0 else 0)
        repartition.append({"membre_id": pid, "part_centimes": part})

    return repartition


def ajouter_depense(
    conn,
    groupe_id: int,
    libelle: str,
    montant_centimes: int,
    date_val: Any,
    payeur_id: int,
    participant_ids: List[int],
) -> int:
    """
    Ajoute une dépense en vérifiant toutes les règles métier :
    - Une dépense a un montant positif et au moins un participant.
    - Le payeur et les participants appartiennent au groupe.
    - La date d’une dépense est comprise dans le séjour, dates de début et de fin incluses.
    - Une dépense est partagée à parts égales entre ses participants.
      Le centime restant va au premier participant ajouté.
    """
    groupe = obtenir_groupe(conn, groupe_id)
    if not groupe:
        raise ValueError(f"Le groupe {groupe_id} n'existe pas.")

    libelle = (libelle or "").strip()
    if not libelle:
        raise ValueError("Le libellé de la dépense ne peut pas être vide.")

    if montant_centimes <= 0:
        raise ValueError("Le montant d'une dépense doit être strictement supérieur à 0 €.")

    if not participant_ids:
        raise ValueError("Une dépense doit avoir au moins un participant.")

    # Validation de la date dans le séjour (inclus)
    date_str = valider_date_format(date_val)
    if date_str < groupe["date_debut"] or date_str > groupe["date_fin"]:
        raise ValueError(
            f"La date de la dépense ({date_str}) doit être comprise dans le séjour "
            f"(du {groupe['date_debut']} au {groupe['date_fin']} inclus)."
        )

    # Validation du payeur et des participants
    membres_groupe = {m["id"]: m["nom"] for m in obtenir_membres(conn, groupe_id)}
    if payeur_id not in membres_groupe:
        raise ValueError("Le payeur doit appartenir au groupe.")

    for pid in participant_ids:
        if pid not in membres_groupe:
            raise ValueError(f"Le participant {pid} n'appartient pas au groupe.")

    # Insertion de la dépense
    cur = conn.execute(
        "INSERT INTO depenses (groupe_id, libelle, montant_centimes, date, payeur_id) "
        "VALUES (?, ?, ?, ?, ?)",
        [groupe_id, libelle, montant_centimes, date_str, payeur_id],
    )
    depense_id = cur.lastrowid

    # Insertion des participants dans l'ordre fourni
    for pid in participant_ids:
        conn.execute(
            "INSERT INTO participants (depense_id, membre_id) VALUES (?, ?)",
            [depense_id, pid],
        )

    conn.commit()
    return depense_id


def modifier_depense(
    conn,
    depense_id: int,
    groupe_id: int,
    libelle: str,
    montant_centimes: int,
    date_val: Any,
    payeur_id: int,
    participant_ids: List[int],
) -> None:
    """
    Modifie une dépense existante en réappliquant toutes les règles métier.
    """
    groupe = obtenir_groupe(conn, groupe_id)
    if not groupe:
        raise ValueError(f"Le groupe {groupe_id} n'existe pas.")

    libelle = (libelle or "").strip()
    if not libelle:
        raise ValueError("Le libellé de la dépense ne peut pas être vide.")

    if montant_centimes <= 0:
        raise ValueError("Le montant d'une dépense doit être strictement supérieur à 0 €.")

    if not participant_ids:
        raise ValueError("Une dépense doit avoir au moins un participant.")

    # Validation de la date dans le séjour (inclus)
    date_str = valider_date_format(date_val)
    if date_str < groupe["date_debut"] or date_str > groupe["date_fin"]:
        raise ValueError(
            f"La date de la dépense ({date_str}) doit être comprise dans le séjour "
            f"(du {groupe['date_debut']} au {groupe['date_fin']} inclus)."
        )

    # Validation du payeur et des participants
    membres_groupe = {m["id"]: m["nom"] for m in obtenir_membres(conn, groupe_id)}
    if payeur_id not in membres_groupe:
        raise ValueError("Le payeur doit appartenir au groupe.")

    for pid in participant_ids:
        if pid not in membres_groupe:
            raise ValueError(f"Le participant {pid} n'appartient pas au groupe.")

    conn.execute(
        "UPDATE depenses SET libelle = ?, montant_centimes = ?, date = ?, payeur_id = ? WHERE id = ?",
        [libelle, montant_centimes, date_str, payeur_id, depense_id],
    )

    # Remplacement des participants dans l'ordre fourni
    conn.execute("DELETE FROM participants WHERE depense_id = ?", [depense_id])
    for pid in participant_ids:
        conn.execute(
            "INSERT INTO participants (depense_id, membre_id) VALUES (?, ?)",
            [depense_id, pid],
        )

    conn.commit()


def supprimer_depense(conn, depense_id: int) -> None:
    """Supprime une dépense et ses participants."""
    conn.execute("DELETE FROM participants WHERE depense_id = ?", [depense_id])
    conn.execute("DELETE FROM depenses WHERE id = ?", [depense_id])
    conn.commit()


def obtenir_depenses(conn, groupe_id: int) -> List[Dict[str, Any]]:
    """
    Récupère toutes les dépenses d'un groupe avec le détail des participants
    et de leur part individuelle calculée.
    """
    rows = conn.execute(
        """
        SELECT d.id, d.groupe_id, d.libelle, d.montant_centimes, d.date, d.payeur_id, m.nom AS payeur_nom
        FROM depenses d
        JOIN membres m ON d.payeur_id = m.id
        WHERE d.groupe_id = ?
        ORDER BY d.date DESC, d.id DESC
        """,
        [groupe_id],
    ).fetchall()

    depenses = []
    for r in rows:
        dep = dict(r)
        # Récupère les participants dans l'ordre d'insertion (rowid)
        part_rows = conn.execute(
            """
            SELECT p.membre_id, m.nom
            FROM participants p
            JOIN membres m ON p.membre_id = m.id
            WHERE p.depense_id = ?
            ORDER BY p.rowid ASC
            """,
            [dep["id"]],
        ).fetchall()

        part_ids = [p["membre_id"] for p in part_rows]
        parts_calculees = (
            calculer_parts_depense(dep["montant_centimes"], part_ids)
            if part_ids
            else []
        )

        parts_map = {item["membre_id"]: item["part_centimes"] for item in parts_calculees}
        dep["participants"] = [
            {
                "id": p["membre_id"],
                "nom": p["nom"],
                "part_centimes": parts_map.get(p["membre_id"], 0),
            }
            for p in part_rows
        ]
        depenses.append(dep)

    return depenses


def calculer_soldes(conn, groupe_id: int) -> Dict[int, Dict[str, Any]]:
    """
    Calcule le solde de chaque membre du groupe :
    - solde = total_paye - total_du
    - exact au centime près
    - la somme des soldes vaut toujours 0
    """
    membres = obtenir_membres(conn, groupe_id)
    soldes = {
        m["id"]: {
            "id": m["id"],
            "nom": m["nom"],
            "paye_centimes": 0,
            "du_centimes": 0,
            "solde_centimes": 0,
        }
        for m in membres
    }

    depenses_rows = conn.execute(
        "SELECT id, montant_centimes, payeur_id FROM depenses WHERE groupe_id = ?",
        [groupe_id],
    ).fetchall()

    for dep in depenses_rows:
        dep_id = dep["id"]
        montant = dep["montant_centimes"]
        payeur_id = dep["payeur_id"]

        if payeur_id in soldes:
            soldes[payeur_id]["paye_centimes"] += montant

        # Participants ordonnés par rowid (ordre d'ajout)
        part_rows = conn.execute(
            "SELECT membre_id FROM participants WHERE depense_id = ? ORDER BY rowid ASC",
            [dep_id],
        ).fetchall()

        part_ids = [p["membre_id"] for p in part_rows]
        if part_ids:
            repartition = calculer_parts_depense(montant, part_ids)
            for rep in repartition:
                pid = rep["membre_id"]
                if pid in soldes:
                    soldes[pid]["du_centimes"] += rep["part_centimes"]

    # Calcul des soldes nets
    somme_soldes = 0
    for m_id, s in soldes.items():
        s["solde_centimes"] = s["paye_centimes"] - s["du_centimes"]
        somme_soldes += s["solde_centimes"]

    # Assertion mathématique de sécurité : la somme des soldes vaut TOUJOURS 0
    if membres and somme_soldes != 0:
        raise AssertionError(f"La somme des soldes est non nulle : {somme_soldes} centimes.")

    return soldes


def calculer_remboursements(soldes: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calcule les virements recommandés pour équilibrer les comptes.
    Algorithme de réduction de dettes équilibrant au centime près.
    """
    debiteurs = []
    crediteurs = []

    for s in soldes.values():
        if s["solde_centimes"] < 0:
            debiteurs.append({"nom": s["nom"], "reste": -s["solde_centimes"]})
        elif s["solde_centimes"] > 0:
            crediteurs.append({"nom": s["nom"], "reste": s["solde_centimes"]})

    debiteurs.sort(key=lambda x: x["reste"], reverse=True)
    crediteurs.sort(key=lambda x: x["reste"], reverse=True)

    remboursements = []
    i, j = 0, 0
    while i < len(debiteurs) and j < len(crediteurs):
        deb = debiteurs[i]
        crd = crediteurs[j]
        montant = min(deb["reste"], crd["reste"])

        if montant > 0:
            remboursements.append({
                "de": deb["nom"],
                "a": crd["nom"],
                "montant_centimes": montant,
            })
            deb["reste"] -= montant
            crd["reste"] -= montant

        if deb["reste"] == 0:
            i += 1
        if crd["reste"] == 0:
            j += 1

    return remboursements


def centimes_en_euros_str(centimes: int, avec_signe: bool = False) -> str:
    """Formate des centimes en euros (ex: '+20,00 €', '30,00 €')."""
    valeur = centimes / 100.0
    if avec_signe:
        return f"{valeur:+.2f} €".replace(".", ",")
    return f"{valeur:.2f} €".replace(".", ",")
