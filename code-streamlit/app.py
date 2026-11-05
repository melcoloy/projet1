import os
if "SSLKEYLOGFILE" in os.environ and "aswMonFlt" in os.environ["SSLKEYLOGFILE"]:
    del os.environ["SSLKEYLOGFILE"]

import io
import csv
from datetime import date
import streamlit as st

from base import ouvrir_base
import modele

# Configuration de la page
st.set_page_config(
    page_title="Partage de frais",
    page_icon="💶",
    layout="wide",
)

# Style personnalisé pour l'interface
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid #e9ecef;
        margin-bottom: 8px;
    }
    .badge-positif {
        color: #198754;
        font-weight: bold;
    }
    .badge-negatif {
        color: #dc3545;
        font-weight: bold;
    }
    .badge-neutre {
        color: #6c757d;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💶 Partage de frais")
st.caption("Noter les dépenses d’un séjour entre amis et savoir à tout moment qui doit combien à qui.")

# Connexion à la base de données
conn = ouvrir_base()

# ==============================================================================
# BARRE LATÉRALE : Gestion et sélection des groupes
# ==============================================================================
st.sidebar.header("🏖️ Séjours & Groupes")

groupes = modele.obtenir_groupes(conn)

# Sélecteur de groupe
options_groupes = {
    g["id"]: f"{g['nom']} ({modele.formater_date_fr(g['date_debut'])} au {modele.formater_date_fr(g['date_fin'])})"
    for g in groupes
}

if "groupe_id" not in st.session_state and groupes:
    st.session_state["groupe_id"] = groupes[0]["id"]

# Si le groupe sélectionné n'existe plus, on prend le premier disponible
if groupes and st.session_state.get("groupe_id") not in options_groupes:
    st.session_state["groupe_id"] = groupes[0]["id"]

if options_groupes:
    groupe_actif_id = st.sidebar.selectbox(
        "Choisir un séjour :",
        options=list(options_groupes.keys()),
        format_func=lambda gid: options_groupes.get(gid, "Séjour inconnu"),
        key="selecteur_groupe",
        index=list(options_groupes.keys()).index(st.session_state["groupe_id"]) if st.session_state.get("groupe_id") in options_groupes else 0,
    )
    st.session_state["groupe_id"] = groupe_actif_id
else:
    groupe_actif_id = None

# Création d'un nouveau groupe
with st.sidebar.expander("➕ Créer un nouveau groupe", expanded=(len(groupes) == 0)):
    with st.form("form_nouveau_groupe"):
        nouveau_nom = st.text_input("Nom du groupe *", placeholder="Ex: Vacances à Rome")
        col_d1, col_d2 = st.columns(2)
        nouvelle_date_debut = col_d1.date_input("Date de début *", value=date.today(), format="DD/MM/YYYY")
        nouvelle_date_fin = col_d2.date_input("Date de fin *", value=date.today(), format="DD/MM/YYYY")
        nouveaux_membres_txt = st.text_area(
            "Membres du groupe (séparés par virgules ou retours à la ligne) *",
            placeholder="Alice\nBob\nChloé",
        )
        btn_creer_groupe = st.form_submit_button("Créer le groupe", type="primary")

        if btn_creer_groupe:
            if not nouveau_nom.strip():
                st.error("Le nom du groupe est obligatoire.")
            elif nouvelle_date_debut > nouvelle_date_fin:
                st.error("La date de début ne peut pas être postérieure à la date de fin.")
            else:
                lignes_membres = [
                    m.strip()
                    for m in nouveaux_membres_txt.replace(",", "\n").split("\n")
                    if m.strip()
                ]
                if not lignes_membres:
                    st.error("Veuillez renseigner au moins un membre.")
                else:
                    try:
                        nouveau_id = modele.creer_groupe(
                            conn,
                            nom=nouveau_nom,
                            date_debut=nouvelle_date_debut,
                            date_fin=nouvelle_date_fin,
                            noms_membres=lignes_membres,
                        )
                        st.session_state["groupe_id"] = nouveau_id
                        st.success("Groupe créé avec succès !")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Erreur lors de la création : {err}")

# Si aucun groupe n'existe, arrêt ici
if not groupe_actif_id:
    st.info("Aucun séjour n'existe actuellement. Utilisez le formulaire dans la barre latérale pour créer votre premier groupe !")
    st.stop()

# Détails du groupe actif
groupe_actif = modele.obtenir_groupe(conn, groupe_actif_id)
membres_actifs = modele.obtenir_membres(conn, groupe_actif_id)
depenses_actives = modele.obtenir_depenses(conn, groupe_actif_id)
soldes_actifs = modele.calculer_soldes(conn, groupe_actif_id)

# Gestion des membres dans la barre latérale
st.sidebar.markdown("---")
st.sidebar.subheader(f"👥 Membres ({len(membres_actifs)})")
for m in membres_actifs:
    st.sidebar.write(f"• {m['nom']}")

with st.sidebar.expander("➕ Ajouter un membre au séjour"):
    with st.form("form_ajouter_membre"):
        nom_nouveau_membre = st.text_input("Nom du membre")
        btn_ajouter_m = st.form_submit_button("Ajouter")
        if btn_ajouter_m:
            try:
                modele.ajouter_membre(conn, groupe_actif_id, nom_nouveau_membre)
                st.success(f"Membre {nom_nouveau_membre} ajouté !")
                st.rerun()
            except Exception as err:
                st.error(str(err))

with st.sidebar.expander("🗑️ Supprimer ce séjour"):
    st.caption("Cette action supprimera définitivement le séjour, ses dépenses et ses membres.")
    confirmer_suppr_groupe = st.checkbox("Confirmer la suppression", key="confirmer_suppression_groupe")
    if st.button("Supprimer définitivement", type="secondary", disabled=not confirmer_suppr_groupe):
        modele.supprimer_groupe(conn, groupe_actif_id)
        st.session_state.pop("groupe_id", None)
        st.session_state.pop("selecteur_groupe", None)
        st.success("Séjour supprimé.")
        st.rerun()

# ==============================================================================
# EN-TÊTE DU GROUPE ACTIF
# ==============================================================================
col_titre, col_dates = st.columns([2, 1])
with col_titre:
    st.subheader(f"🌴 {groupe_actif['nom']}")
with col_dates:
    st.markdown(
        f"**Dates du séjour :**\nDu `{modele.formater_date_fr(groupe_actif['date_debut'])}` "
        f"au `{modele.formater_date_fr(groupe_actif['date_fin'])}`"
    )

total_depenses_centimes = sum(d["montant_centimes"] for d in depenses_actives)
nb_membres = len(membres_actifs)

m1, m2, m3 = st.columns(3)
m1.metric("Total dépensé", modele.centimes_en_euros_str(total_depenses_centimes))
m2.metric("Nombre de dépenses", len(depenses_actives))
m3.metric("Membres", nb_membres)

st.markdown("---")

# ==============================================================================
# ONGLETS PRINCIPAUX
# ==============================================================================
tab_soldes, tab_ajouter_depense, tab_liste_depenses, tab_export = st.tabs([
    "📊 Soldes des membres",
    "➕ Ajouter une dépense",
    "📋 Liste des dépenses",
    "📥 Exporter",
])

# ------------------------------------------------------------------------------
# ONGLET 1 : SOLDES & ÉQUILIBRE
# ------------------------------------------------------------------------------
with tab_soldes:
    st.markdown("### Solde de chaque membre")
    st.caption(
        "Un solde **positif** signifie qu'on doit de l'argent à ce membre (créditeur). "
        "Un solde **négatif** signifie que ce membre doit de l'argent au groupe (débiteur)."
    )

    if not membres_actifs:
        st.warning("Ce groupe n'a pas encore de membres.")
    else:
        # Affichage clair sous forme de tableau
        lignes_tableau = []
        for s in soldes_actifs.values():
            solde_cts = s["solde_centimes"]
            if solde_cts > 0:
                statut = f"🟢 Créditeur (+{modele.centimes_en_euros_str(solde_cts)})"
            elif solde_cts < 0:
                statut = f"🔴 Débiteur ({modele.centimes_en_euros_str(solde_cts)})"
            else:
                statut = "⚪ Équilibré (0,00 €)"

            lignes_tableau.append({
                "Membre": s["nom"],
                "Total payé": modele.centimes_en_euros_str(s["paye_centimes"]),
                "Total dû": modele.centimes_en_euros_str(s["du_centimes"]),
                "Solde net": modele.centimes_en_euros_str(solde_cts, avec_signe=True),
                "Statut": statut,
            })

        st.dataframe(lignes_tableau, use_container_width=True)

        # Section des remboursements suggérés (Qui doit rembourser qui ?)
        st.markdown("### 🤝 Remboursements suggérés")
        remboursements = modele.calculer_remboursements(soldes_actifs)

        if not remboursements:
            st.info("Tous les comptes sont équilibrés ! Aucun remboursement n'est nécessaire.")
        else:
            st.write("Voici la façon la plus simple d'équilibrer les comptes :")
            for r in remboursements:
                st.markdown(
                    f"- **{r['de']}** doit rembourser **{modele.centimes_en_euros_str(r['montant_centimes'])}** à **{r['a']}**"
                )

# ------------------------------------------------------------------------------
# ONGLET 2 : AJOUTER UNE DÉPENSE
# ------------------------------------------------------------------------------
with tab_ajouter_depense:
    st.markdown("### Enregistrer une nouvelle dépense")

    if not membres_actifs:
        st.warning("Ajoutez d'abord des membres au groupe pour pouvoir enregistrer une dépense.")
    else:
        # Convertir les dates du séjour pour initialiser le sélecteur
        debut_sejour = date.fromisoformat(groupe_actif["date_debut"])
        fin_sejour = date.fromisoformat(groupe_actif["date_fin"])
        aujourdhui = date.today()
        # Date par défaut comprise dans le séjour
        date_defaut = aujourdhui if (debut_sejour <= aujourdhui <= fin_sejour) else debut_sejour

        with st.form("form_nouvelle_depense", clear_on_submit=True):
            libelle = st.text_input("Libellé de la dépense *", placeholder="Ex: Courses, Restaurant, Plein d'essence, Musée...")

            col_m, col_d = st.columns(2)
            montant_saisi = col_m.number_input(
                "Montant en euros (€) *",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.2f",
                help="Le montant doit être strictement supérieur à 0 €.",
            )

            date_depense = col_d.date_input(
                "Date de la dépense *",
                value=date_defaut,
                format="DD/MM/YYYY",
                help=(
                    f"La date doit être comprise dans le séjour : du "
                    f"{modele.formater_date_fr(groupe_actif['date_debut'])} au "
                    f"{modele.formater_date_fr(groupe_actif['date_fin'])} inclus."
                ),
            )

            # Sélection du payeur
            payeur = st.selectbox(
                "Payeur (qui a réglé la dépense ?) *",
                options=membres_actifs,
                format_func=lambda m: m["nom"],
            )

            # Sélection des participants
            st.write("**Participants (qui partage cette dépense ?) ***")
            st.caption(
                "💡 *Règle : La dépense est partagée à parts égales. "
                "Le centime restant va au premier participant ajouté.*"
            )

            participants_selectionnes = st.multiselect(
                "Sélectionnez les participants (dans l'ordre souhaité) :",
                options=membres_actifs,
                default=membres_actifs,
                format_func=lambda m: m["nom"],
            )

            # Prévisualisation du partage
            if montant_saisi > 0 and participants_selectionnes:
                montant_cts = int(round(montant_saisi * 100))
                p_ids = [p["id"] for p in participants_selectionnes]
                repartition = modele.calculer_parts_depense(montant_cts, p_ids)
                id_to_nom = {m["id"]: m["nom"] for m in membres_actifs}
                apercu_parts = [
                    f"{id_to_nom[r['membre_id']]}: {modele.centimes_en_euros_str(r['part_centimes'])}"
                    for r in repartition
                ]
                st.info(f"🔎 **Aperçu du partage :** {', '.join(apercu_parts)}")

            btn_ajouter_depense = st.form_submit_button("Ajouter la dépense", type="primary")

            if btn_ajouter_depense:
                montant_centimes = int(round(montant_saisi * 100))
                participant_ids = [p["id"] for p in participants_selectionnes]
                date_str = date_depense.isoformat()

                # Validations avec messages d'erreurs clairs
                erreurs = []
                if not libelle.strip():
                    erreurs.append("Le libellé de la dépense ne peut pas être vide.")
                if montant_centimes <= 0:
                    erreurs.append("Une dépense doit avoir un montant strictement positif (> 0 €).")
                if not participant_ids:
                    erreurs.append("Une dépense doit avoir au moins un participant.")
                if date_str < groupe_actif["date_debut"] or date_str > groupe_actif["date_fin"]:
                    erreurs.append(
                        f"La date de la dépense ({modele.formater_date_fr(date_str)}) est hors séjour. "
                        f"Elle doit être comprise entre le {modele.formater_date_fr(groupe_actif['date_debut'])} "
                        f"et le {modele.formater_date_fr(groupe_actif['date_fin'])} inclus."
                    )
                if not payeur:
                    erreurs.append("Veuillez sélectionner un payeur appartenant au groupe.")

                if erreurs:
                    for err in erreurs:
                        st.error(f"❌ {err} (Dépense refusée, soldes inchangés)")
                else:
                    try:
                        modele.ajouter_depense(
                            conn,
                            groupe_id=groupe_actif_id,
                            libelle=libelle,
                            montant_centimes=montant_centimes,
                            date_val=date_str,
                            payeur_id=payeur["id"],
                            participant_ids=participant_ids,
                        )
                        st.success("✅ Dépense enregistrée avec succès !")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"❌ Erreur lors de l'enregistrement : {ex} (Soldes inchangés)")

# ------------------------------------------------------------------------------
# ONGLET 3 : LISTE & SUPPRESSION DES DÉPENSES
# ------------------------------------------------------------------------------
with tab_liste_depenses:
    st.markdown("### Dépenses enregistrées")

    if not depenses_actives:
        st.info("Aucune dépense enregistrée pour ce séjour pour le moment.")
    else:
        # Filtres : par membre, par période et recherche textuelle
        col_filtre_m, col_recherche = st.columns(2)
        filtre_membre = col_filtre_m.selectbox(
            "Filtrer par membre (payeur ou participant) :",
            options=["Tous les membres"] + [m["nom"] for m in membres_actifs],
        )
        recherche_texte = col_recherche.text_input(
            "Rechercher par libellé :",
            placeholder="Ex: courses, essence...",
        ).strip().lower()

        col_p1, col_p2 = st.columns(2)
        filtre_date_min = col_p1.date_input(
            "À partir du :",
            value=date.fromisoformat(groupe_actif["date_debut"]),
            min_value=date.fromisoformat(groupe_actif["date_debut"]),
            max_value=date.fromisoformat(groupe_actif["date_fin"]),
            format="DD/MM/YYYY",
            key="filtre_d_min",
        )
        filtre_date_max = col_p2.date_input(
            "Jusqu'au :",
            value=date.fromisoformat(groupe_actif["date_fin"]),
            min_value=date.fromisoformat(groupe_actif["date_debut"]),
            max_value=date.fromisoformat(groupe_actif["date_fin"]),
            format="DD/MM/YYYY",
            key="filtre_d_max",
        )

        depenses_filtrees = []
        for dep in depenses_actives:
            # Filtre membre
            concerne_membre = True
            if filtre_membre != "Tous les membres":
                noms_participants = [p["nom"] for p in dep["participants"]]
                concerne_membre = (dep["payeur_nom"] == filtre_membre) or (filtre_membre in noms_participants)

            # Filtre texte
            concerne_texte = True
            if recherche_texte:
                concerne_texte = recherche_texte in dep["libelle"].lower()

            # Filtre période
            dep_date = date.fromisoformat(dep["date"])
            concerne_periode = filtre_date_min <= dep_date <= filtre_date_max

            if concerne_membre and concerne_texte and concerne_periode:
                depenses_filtrees.append(dep)

        st.caption(f"Affichage de {len(depenses_filtrees)} dépense(s) sur {len(depenses_actives)}")

        for dep in depenses_filtrees:
            montant_str = modele.centimes_en_euros_str(dep["montant_centimes"])
            with st.container():
                col_info, col_actions = st.columns([4, 2])
                with col_info:
                    st.markdown(f"#### 💳 {dep['libelle']} — **{montant_str}**")
                    st.write(
                        f"📅 **Date :** `{modele.formater_date_fr(dep['date'])}` &nbsp;|&nbsp; "
                        f"👤 **Payeur :** **{dep['payeur_nom']}**"
                    )

                    # Détail des parts
                    details_parts = [
                        f"{p['nom']} ({modele.centimes_en_euros_str(p['part_centimes'])})"
                        for p in dep["participants"]
                    ]
                    st.caption(f"**Partagé entre ({len(dep['participants'])}) :** {', '.join(details_parts)}")

                with col_actions:
                    st.write("")
                    c_btn_edit, c_btn_suppr = st.columns(2)
                    cle_edition = f"edit_active_{dep['id']}"
                    if cle_edition not in st.session_state:
                        st.session_state[cle_edition] = False

                    if c_btn_edit.button("✏️ Modifier", key=f"btn_edit_{dep['id']}"):
                        st.session_state[cle_edition] = not st.session_state[cle_edition]
                        st.rerun()

                    if c_btn_suppr.button("🗑️ Supprimer", key=f"btn_suppr_{dep['id']}", type="secondary"):
                        modele.supprimer_depense(conn, dep["id"])
                        st.toast(f"Dépense '{dep['libelle']}' supprimée.")
                        st.rerun()

                # Formulaire d'édition si activé
                if st.session_state.get(cle_edition, False):
                    with st.expander(f"✏️ Modifier la dépense '{dep['libelle']}'", expanded=True):
                        with st.form(f"form_modif_{dep['id']}"):
                            edit_libelle = st.text_input("Libellé", value=dep["libelle"])
                            c_em, c_ed = st.columns(2)
                            edit_montant = c_em.number_input(
                                "Montant (€)",
                                min_value=0.01,
                                value=float(dep["montant_centimes"] / 100.0),
                                step=1.0,
                                format="%.2f",
                            )
                            edit_date = c_ed.date_input(
                                "Date",
                                value=date.fromisoformat(dep["date"]),
                                min_value=date.fromisoformat(groupe_actif["date_debut"]),
                                max_value=date.fromisoformat(groupe_actif["date_fin"]),
                                format="DD/MM/YYYY",
                            )

                            # Payeur actuel
                            idx_payeur = 0
                            for i, m in enumerate(membres_actifs):
                                if m["id"] == dep["payeur_id"]:
                                    idx_payeur = i
                                    break
                            edit_payeur = st.selectbox(
                                "Payeur",
                                options=membres_actifs,
                                index=idx_payeur,
                                format_func=lambda m: m["nom"],
                            )

                            # Participants actuels
                            ids_actuels = [p["id"] for p in dep["participants"]]
                            parts_par_defaut = [m for m in membres_actifs if m["id"] in ids_actuels]
                            edit_participants = st.multiselect(
                                "Participants (le premier reçoit le centime restant)",
                                options=membres_actifs,
                                default=parts_par_defaut,
                                format_func=lambda m: m["nom"],
                            )

                            c_save, c_cancel = st.columns(2)
                            btn_sauver = c_save.form_submit_button("Enregistrer les modifications", type="primary")
                            btn_annuler = c_cancel.form_submit_button("Annuler")

                            if btn_sauver:
                                try:
                                    edit_centimes = int(round(edit_montant * 100))
                                    edit_p_ids = [p["id"] for p in edit_participants]
                                    modele.modifier_depense(
                                        conn,
                                        depense_id=dep["id"],
                                        groupe_id=groupe_actif_id,
                                        libelle=edit_libelle,
                                        montant_centimes=edit_centimes,
                                        date_val=edit_date.isoformat(),
                                        payeur_id=edit_payeur["id"],
                                        participant_ids=edit_p_ids,
                                    )
                                    st.session_state[cle_edition] = False
                                    st.success("Dépense modifiée avec succès !")
                                    st.rerun()
                                except Exception as e_mod:
                                    st.error(f"Erreur : {e_mod}")
                            elif btn_annuler:
                                st.session_state[cle_edition] = False
                                st.rerun()

                st.markdown("---")

# ------------------------------------------------------------------------------
# ONGLET 4 : EXPORT CSV (BONUS)
# ------------------------------------------------------------------------------
with tab_export:
    st.markdown("### 📥 Exporter les données du séjour")

    # 1. Export des dépenses en CSV
    if depenses_actives:
        output_dep = io.StringIO()
        writer_dep = csv.writer(output_dep, delimiter=";")
        writer_dep.writerow(["ID", "Date", "Libellé", "Montant_EUR", "Payeur", "Participants_et_parts"])
        for d in depenses_actives:
            parts_str = ", ".join(
                f"{p['nom']} ({modele.centimes_en_euros_str(p['part_centimes'])})"
                for p in d["participants"]
            )
            writer_dep.writerow([
                d["id"],
                modele.formater_date_fr(d["date"]),
                d["libelle"],
                f"{d['montant_centimes'] / 100:.2f}",
                d["payeur_nom"],
                parts_str,
            ])

        st.download_button(
            label="📄 Télécharger les dépenses en CSV",
            data=output_dep.getvalue().encode("utf-8-sig"),
            file_name=f"depenses_{groupe_actif['nom'].replace(' ', '_')}.csv",
            mime="text/csv",
        )

    # 2. Export des soldes en CSV
    if soldes_actifs:
        output_soldes = io.StringIO()
        writer_soldes = csv.writer(output_soldes, delimiter=";")
        writer_soldes.writerow(["Membre", "Total_Paye_EUR", "Total_Du_EUR", "Solde_Net_EUR"])
        for s in soldes_actifs.values():
            writer_soldes.writerow([
                s["nom"],
                f"{s['paye_centimes'] / 100:.2f}",
                f"{s['du_centimes'] / 100:.2f}",
                f"{s['solde_centimes'] / 100:.2f}",
            ])

        st.download_button(
            label="📊 Télécharger les soldes en CSV",
            data=output_soldes.getvalue().encode("utf-8-sig"),
            file_name=f"soldes_{groupe_actif['nom'].replace(' ', '_')}.csv",
            mime="text/csv",
        )

# Fermeture propre de la connexion SQLite
conn.close()
