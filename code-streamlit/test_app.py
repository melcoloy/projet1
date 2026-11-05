import os
if "SSLKEYLOGFILE" in os.environ and "aswMonFlt" in os.environ["SSLKEYLOGFILE"]:
    del os.environ["SSLKEYLOGFILE"]

import sqlite3
import sys
from pathlib import Path

# Assure l'accès aux modules locaux
RACINE = Path(__file__).parent.parent
DOSSIER_STREAMLIT = Path(__file__).parent
if str(DOSSIER_STREAMLIT) not in sys.path:
    sys.path.insert(0, str(DOSSIER_STREAMLIT))

from streamlit.testing.v1 import AppTest
import modele


def creer_base_de_test():
    """Crée une base SQLite en mémoire avec le schéma de base.sql."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    sql = (RACINE / "base.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def test_accueil():
    """Vérifie que l'interface Streamlit se lance sans lever d'exception."""
    page = AppTest.from_file(str(DOSSIER_STREAMLIT / "app.py"), default_timeout=60).run()
    assert not page.exception


def test_regle_alice_30_euros():
    """
    Règle vérifiée :
    Alice paie 30 € pour Alice, Bob et Chloé.
    Résultat attendu : Alice +20,00 ; Bob -10,00 ; Chloé -10,00.
    """
    conn = creer_base_de_test()
    # Le groupe 1 dans base.sql contient déjà cette dépense
    soldes = modele.calculer_soldes(conn, 1)

    assert soldes[1]["solde_centimes"] == 2000
    assert soldes[2]["solde_centimes"] == -1000
    assert soldes[3]["solde_centimes"] == -1000

    # Vérification des sommes
    assert sum(s["solde_centimes"] for s in soldes.values()) == 0


def test_regle_depense_hors_sejour_refusee():
    """
    Règle vérifiée :
    Une dépense datée hors du séjour est refusée, soldes inchangés.
    """
    conn = creer_base_de_test()
    soldes_avant = modele.calculer_soldes(conn, 1)

    # Date avant le début du séjour (séjour: 2026-07-01 au 2026-07-08)
    try:
        modele.ajouter_depense(
            conn,
            groupe_id=1,
            libelle="Restaurant trop tôt",
            montant_centimes=2500,
            date_val="2026-06-30",
            payeur_id=1,
            participant_ids=[1, 2],
        )
        assert False, "La dépense antérieure au séjour aurait dû être refusée."
    except ValueError as e:
        assert "comprise dans le séjour" in str(e)

    # Date après la fin du séjour
    try:
        modele.ajouter_depense(
            conn,
            groupe_id=1,
            libelle="Activité trop tard",
            montant_centimes=2500,
            date_val="2026-07-09",
            payeur_id=1,
            participant_ids=[1, 2],
        )
        assert False, "La dépense postérieure au séjour aurait dû être refusée."
    except ValueError as e:
        assert "comprise dans le séjour" in str(e)

    # Soldes inchangés
    soldes_apres = modele.calculer_soldes(conn, 1)
    for mid in soldes_avant:
        assert soldes_avant[mid]["solde_centimes"] == soldes_apres[mid]["solde_centimes"]


def test_regle_depense_zero_ou_negative_refusee():
    """
    Règle vérifiée :
    Une dépense a un montant positif. Une dépense de 0 € ou négative est refusée, soldes inchangés.
    """
    conn = creer_base_de_test()
    soldes_avant = modele.calculer_soldes(conn, 1)

    # Montant 0 €
    try:
        modele.ajouter_depense(
            conn,
            groupe_id=1,
            libelle="Dépense 0 €",
            montant_centimes=0,
            date_val="2026-07-03",
            payeur_id=1,
            participant_ids=[1, 2, 3],
        )
        assert False, "Une dépense de 0 € aurait dû être refusée."
    except ValueError as e:
        assert "strictement supérieur à 0" in str(e)

    # Montant négatif
    try:
        modele.ajouter_depense(
            conn,
            groupe_id=1,
            libelle="Dépense négative",
            montant_centimes=-500,
            date_val="2026-07-03",
            payeur_id=1,
            participant_ids=[1, 2, 3],
        )
        assert False, "Une dépense négative aurait dû être refusée."
    except ValueError as e:
        assert "strictement supérieur à 0" in str(e)

    # Soldes inchangés
    soldes_apres = modele.calculer_soldes(conn, 1)
    for mid in soldes_avant:
        assert soldes_avant[mid]["solde_centimes"] == soldes_apres[mid]["solde_centimes"]


def test_regle_depense_sans_participant_refusee():
    """Une dépense sans participant doit être refusée."""
    conn = creer_base_de_test()
    try:
        modele.ajouter_depense(
            conn,
            groupe_id=1,
            libelle="Personne",
            montant_centimes=1000,
            date_val="2026-07-04",
            payeur_id=1,
            participant_ids=[],
        )
        assert False, "Une dépense sans participant aurait dû être refusée."
    except ValueError as e:
        assert "au moins un participant" in str(e)


def test_regle_nouveau_groupe_10_euros():
    """
    Règle vérifiée :
    Sur un nouveau groupe, Alice paie 10 € pour les trois (Alice, Bob, Chloé).
    Résultat attendu : Alice +6,66 ; Bob -3,33 ; Chloé -3,33.
    Le centime restant va au premier participant ajouté (Alice).
    """
    conn = creer_base_de_test()
    gid = modele.creer_groupe(
        conn,
        nom="Nouveau groupe",
        date_debut="2026-08-01",
        date_fin="2026-08-10",
        noms_membres=["Alice", "Bob", "Chloé"],
    )

    membres = modele.obtenir_membres(conn, gid)
    a_id = [m["id"] for m in membres if m["nom"] == "Alice"][0]
    b_id = [m["id"] for m in membres if m["nom"] == "Bob"][0]
    c_id = [m["id"] for m in membres if m["nom"] == "Chloé"][0]

    # Alice paie 10 € (1000 centimes) pour Alice, Bob et Chloé
    modele.ajouter_depense(
        conn,
        groupe_id=gid,
        libelle="Pic-nique 10 €",
        montant_centimes=1000,
        date_val="2026-08-02",
        payeur_id=a_id,
        participant_ids=[a_id, b_id, c_id],
    )

    soldes = modele.calculer_soldes(conn, gid)
    assert soldes[a_id]["solde_centimes"] == 666
    assert soldes[b_id]["solde_centimes"] == -333
    assert soldes[c_id]["solde_centimes"] == -333
    assert sum(s["solde_centimes"] for s in soldes.values()) == 0


def test_supprimer_depense():
    """Vérifie la suppression d'une dépense et la mise à jour immédiate des soldes."""
    conn = creer_base_de_test()
    # Dans le groupe 1, il y a la dépense 1 (30 €)
    soldes_initial = modele.calculer_soldes(conn, 1)
    assert soldes_initial[1]["solde_centimes"] == 2000

    # Supprime la dépense 1
    modele.supprimer_depense(conn, 1)

    # Tous les soldes doivent repasser à 0
    soldes_apres = modele.calculer_soldes(conn, 1)
    for s in soldes_apres.values():
        assert s["solde_centimes"] == 0
        assert s["paye_centimes"] == 0
        assert s["du_centimes"] == 0


def test_modifier_depense():
    """Vérifie la modification d'une dépense existante."""
    conn = creer_base_de_test()
    # Dépense 1 : Alice paie 30 € pour Alice, Bob, Chloé
    # On la modifie : Alice paie 45 € pour Bob et Chloé uniquement (Alice ne participe plus)
    modele.modifier_depense(
        conn,
        depense_id=1,
        groupe_id=1,
        libelle="Courses luxe",
        montant_centimes=4500,
        date_val="2026-07-03",
        payeur_id=1,
        participant_ids=[2, 3],
    )
    soldes = modele.calculer_soldes(conn, 1)
    # Alice a payé 4500, doit 0 => solde = +4500
    assert soldes[1]["solde_centimes"] == 4500
    # 4500 / 2 = 2250 chacun
    assert soldes[2]["solde_centimes"] == -2250
    assert soldes[3]["solde_centimes"] == -2250
    assert sum(s["solde_centimes"] for s in soldes.values()) == 0


def test_somme_soldes_toujours_zero():
    """Vérifie que la somme des soldes vaut toujours 0 quelles que soient les dépenses."""
    conn = creer_base_de_test()
    # Ajoutons plusieurs dépenses hétérogènes
    # Bob paie 17,99 € (1799 centimes) pour Bob et Chloé
    modele.ajouter_depense(conn, 1, "Courses bio", 1799, "2026-07-03", 2, [2, 3])
    # Chloé paie 41,27 € (4127 centimes) pour Alice, Bob et Chloé
    modele.ajouter_depense(conn, 1, "Plein essence", 4127, "2026-07-05", 3, [1, 2, 3])

    soldes = modele.calculer_soldes(conn, 1)
    total_soldes = sum(s["solde_centimes"] for s in soldes.values())
    assert total_soldes == 0


def test_remboursements_recommandes():
    """Vérifie que les remboursements suggérés équilibrent bien les dettes."""
    conn = creer_base_de_test()
    soldes = modele.calculer_soldes(conn, 1)
    remboursements = modele.calculer_remboursements(soldes)

    assert len(remboursements) == 2
    # Bob et Chloé doivent chacun 10,00 € à Alice
    bobs = [r for r in remboursements if r["de"] == "Bob"]
    chloes = [r for r in remboursements if r["de"] == "Chloé"]
    assert len(bobs) == 1 and bobs[0]["a"] == "Alice" and bobs[0]["montant_centimes"] == 1000
    assert len(chloes) == 1 and chloes[0]["a"] == "Alice" and chloes[0]["montant_centimes"] == 1000


def test_format_date_fr():
    """Vérifie le formatage des dates au format DD/MM/YYYY."""
    assert modele.formater_date_fr("2026-07-02") == "02/07/2026"
    assert modele.formater_date_fr("2026-12-31") == "31/12/2026"
    from datetime import date
    assert modele.formater_date_fr(date(2026, 7, 2)) == "02/07/2026"


if __name__ == "__main__":
    # Permet de lancer directement les tests via 'python test_app.py'
    tests = [
        test_regle_alice_30_euros,
        test_regle_depense_hors_sejour_refusee,
        test_regle_depense_zero_ou_negative_refusee,
        test_regle_depense_sans_participant_refusee,
        test_regle_nouveau_groupe_10_euros,
        test_supprimer_depense,
        test_modifier_depense,
        test_somme_soldes_toujours_zero,
        test_remboursements_recommandes,
        test_format_date_fr,
        test_accueil,
    ]
    succes = 0
    for t in tests:
        try:
            t()
            print(f"PASS : {t.__name__}")
            succes += 1
        except Exception as err:
            print(f"FAIL : {t.__name__} - {err}")
            raise
    print(f"\nTous les tests ({succes}/{len(tests)}) ont réussi avec succès !")
