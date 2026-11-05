import streamlit as st
from datetime import date

from base import ouvrir_base
from calculs import (
    calculer_soldes,
    raisons_de_ne_pas_supprimer,
    stats_membres,
    valider_depense,
    valider_nom_membre,
)

st.set_page_config(page_title="Partage de frais", layout="centered")
st.title("Partage de frais")

# --- Sélection / création de groupe ---
with ouvrir_base() as conn:
    groupes = conn.execute("SELECT id, nom, date_debut, date_fin FROM groupes").fetchall()

noms = [g["nom"] for g in groupes]
choix = st.sidebar.selectbox("Groupe", noms + ["+ Nouveau groupe"])

if choix == "+ Nouveau groupe":
    st.header("Créer un groupe")
    with st.form("creer_groupe"):
        nom_g = st.text_input("Nom")
        debut = st.date_input("Date de début", value=date.today())
        fin = st.date_input("Date de fin", value=date.today())
        if st.form_submit_button("Créer"):
            if not nom_g.strip():
                st.error("Le nom est obligatoire.")
            elif fin < debut:
                st.error("La date de fin doit être après le début.")
            else:
                with ouvrir_base() as conn:
                    conn.execute(
                        "INSERT INTO groupes (nom, date_debut, date_fin) VALUES (?,?,?)",
                        [nom_g.strip(), str(debut), str(fin)],
                    )
                st.rerun()
    st.stop()

groupe = next(g for g in groupes if g["nom"] == choix)
groupe_id = groupe["id"]
date_debut = date.fromisoformat(groupe["date_debut"])
date_fin = date.fromisoformat(groupe["date_fin"])

st.sidebar.caption(f"Du {groupe['date_debut']} au {groupe['date_fin']}")

with ouvrir_base() as conn:
    membres = conn.execute(
        "SELECT id, nom FROM membres WHERE groupe_id = ? ORDER BY id",
        [groupe_id],
    ).fetchall()

tab_membres, tab_depenses, tab_soldes = st.tabs(["Membres", "Dépenses", "Soldes"])

# === Membres ===
with tab_membres:
    st.subheader("Membres")

    if not membres:
        st.info("Aucun membre pour l'instant.")
    else:
        with ouvrir_base() as conn:
            stats = stats_membres(conn, groupe_id)

        for m in membres:
            s = stats[m["id"]]
            with st.expander(f"{m['nom']} — {s['paye'] / 100:.2f} € payés"):
                st.caption(
                    f"{s['nb_payees']} dépense(s) payée(s)"
                    f" · participe à {s['nb_participations']} dépense(s)"
                )

                col_nom, col_suppr = st.columns([3, 1])

                with col_nom:
                    with st.form(f"renommer_{m['id']}"):
                        nouveau_nom = st.text_input("Nom", value=m["nom"])
                        renomme = st.form_submit_button("Renommer")
                    if renomme:
                        autres = [a["nom"] for a in membres if a["id"] != m["id"]]
                        erreurs = valider_nom_membre(nouveau_nom, autres)
                        if erreurs:
                            for e in erreurs:
                                st.error(e)
                        elif nouveau_nom.strip() == m["nom"]:
                            st.info("Le nom n'a pas changé.")
                        else:
                            with ouvrir_base() as conn:
                                conn.execute(
                                    "UPDATE membres SET nom = ? WHERE id = ?",
                                    [nouveau_nom.strip(), m["id"]],
                                )
                            st.rerun()

                with col_suppr:
                    raisons = raisons_de_ne_pas_supprimer(s)
                    if raisons:
                        st.button("Supprimer", key=f"suppr_{m['id']}", disabled=True)
                        st.caption("Rattaché à : " + ", ".join(raisons))
                    elif st.button("Supprimer", key=f"suppr_{m['id']}"):
                        with ouvrir_base() as conn:
                            conn.execute("DELETE FROM membres WHERE id = ?", [m["id"]])
                        st.rerun()

    st.subheader("Ajouter un membre")
    with st.form("ajout_membre"):
        nom_m = st.text_input("Nouveau membre")
        ajoute = st.form_submit_button("Ajouter")
    if ajoute:
        erreurs = valider_nom_membre(nom_m, [m["nom"] for m in membres])
        if erreurs:
            for e in erreurs:
                st.error(e)
        else:
            with ouvrir_base() as conn:
                conn.execute(
                    "INSERT INTO membres (groupe_id, nom) VALUES (?,?)",
                    [groupe_id, nom_m.strip()],
                )
            st.rerun()

# === Dépenses ===
with tab_depenses:
    st.subheader("Ajouter une dépense")

    if not membres:
        st.warning("Ajoutez d'abord des membres avant de saisir des dépenses.")
    else:
        ids_m = [m["id"] for m in membres]
        noms_m = {m["id"]: m["nom"] for m in membres}

        with st.form("ajout_depense"):
            libelle = st.text_input("Libellé")
            montant = st.number_input("Montant (€)", min_value=0.01, step=0.01, format="%.2f", value=1.00)
            date_dep = st.date_input("Date", value=date_debut, min_value=date_debut, max_value=date_fin)
            payeur_id = st.selectbox("Payeur", ids_m, format_func=lambda i: noms_m[i])
            part_ids = st.multiselect(
                "Participants",
                ids_m,
                default=ids_m,
                format_func=lambda i: noms_m[i],
            )
            submitted = st.form_submit_button("Ajouter")

        if submitted:
            d_str = str(date_dep)
            montant_c = int(round(montant * 100))
            erreurs = valider_depense(
                libelle, montant_c, d_str, part_ids, groupe["date_debut"], groupe["date_fin"]
            )
            if erreurs:
                for e in erreurs:
                    st.error(e)
            else:
                with ouvrir_base() as conn:
                    cur = conn.execute(
                        "INSERT INTO depenses (groupe_id, libelle, montant_centimes, date, payeur_id) VALUES (?,?,?,?,?)",
                        [groupe_id, libelle.strip(), montant_c, d_str, payeur_id],
                    )
                    dep_id = cur.lastrowid
                    for mid in part_ids:
                        conn.execute(
                            "INSERT INTO participants (depense_id, membre_id) VALUES (?,?)",
                            [dep_id, mid],
                        )
                st.success("Dépense ajoutée.")
                st.rerun()

    st.subheader("Liste des dépenses")
    with ouvrir_base() as conn:
        depenses = conn.execute(
            """SELECT d.id, d.libelle, d.montant_centimes, d.date, m.nom AS payeur
               FROM depenses d
               JOIN membres m ON d.payeur_id = m.id
               WHERE d.groupe_id = ?
               ORDER BY d.date, d.id""",
            [groupe_id],
        ).fetchall()

    if not depenses:
        st.info("Aucune dépense.")
    else:
        for dep in depenses:
            with ouvrir_base() as conn:
                parts = conn.execute(
                    """SELECT m.nom FROM participants p
                       JOIN membres m ON p.membre_id = m.id
                       WHERE p.depense_id = ?
                       ORDER BY p.rowid""",
                    [dep["id"]],
                ).fetchall()
            part_noms = ", ".join(p["nom"] for p in parts)
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(
                    f"**{dep['libelle']}** — {dep['montant_centimes']/100:.2f} €"
                    f" — payé par {dep['payeur']} — {dep['date']}"
                )
                st.caption(f"Participants : {part_noms}")
            with col2:
                if st.button("🗑", key=f"del_{dep['id']}"):
                    with ouvrir_base() as conn:
                        conn.execute("DELETE FROM depenses WHERE id = ?", [dep["id"]])
                    st.rerun()

# === Soldes ===
with tab_soldes:
    st.subheader("Soldes")

    if not membres:
        st.info("Aucun membre.")
    else:
        with ouvrir_base() as conn:
            soldes = calculer_soldes(conn, groupe_id)

        for m in membres:
            s = soldes[m["id"]]
            signe = "+" if s >= 0 else ""
            if s > 0:
                st.success(f"{m['nom']} : {signe}{s/100:.2f} €")
            elif s < 0:
                st.error(f"{m['nom']} : {signe}{s/100:.2f} €")
            else:
                st.info(f"{m['nom']} : {signe}{s/100:.2f} €")
