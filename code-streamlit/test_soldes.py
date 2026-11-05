"""Vérifications du tableau 3 de l'énoncé : groupe Alice, Bob, Chloé du 2026-07-01 au 2026-07-08."""

import sqlite3
from pathlib import Path

import pytest

from calculs import (
    calculer_soldes,
    raisons_de_ne_pas_supprimer,
    repartir,
    stats_membres,
    valider_depense,
    valider_nom_membre,
)

SCHEMA = (Path(__file__).parent.parent / "base.sql").read_text(encoding="utf-8")
ALICE, BOB, CHLOE = 1, 2, 3
DEBUT, FIN = "2026-07-01", "2026-07-08"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute("DELETE FROM participants")
    c.execute("DELETE FROM depenses")
    yield c
    c.close()


def ajouter(conn, montant, participants, payeur=ALICE, date="2026-07-02"):
    cur = conn.execute(
        "INSERT INTO depenses (groupe_id, libelle, montant_centimes, date, payeur_id)"
        " VALUES (1,'test',?,?,?)",
        [montant, date, payeur],
    )
    for mid in participants:
        conn.execute(
            "INSERT INTO participants (depense_id, membre_id) VALUES (?,?)",
            [cur.lastrowid, mid],
        )


# --- Tableau 3 : les lignes s'enchaînent ---


def test_alice_paie_30_pour_trois(conn):
    ajouter(conn, 3000, [ALICE, BOB, CHLOE])
    assert calculer_soldes(conn, 1) == {ALICE: 2000, BOB: -1000, CHLOE: -1000}


def test_depense_hors_sejour_refusee(conn):
    erreurs = valider_depense("Resto", 2000, "2026-07-09", [ALICE, BOB], DEBUT, FIN)
    assert erreurs == [f"La date doit être entre {DEBUT} et {FIN}."]


def test_depense_de_zero_refusee(conn):
    erreurs = valider_depense("Rien", 0, "2026-07-02", [ALICE], DEBUT, FIN)
    assert erreurs == ["Le montant doit être positif."]


def test_alice_paie_10_pour_trois_centime_au_premier(conn):
    ajouter(conn, 1000, [ALICE, BOB, CHLOE])
    assert calculer_soldes(conn, 1) == {ALICE: 666, BOB: -333, CHLOE: -333}


# --- Règles ---


def test_repartition_centime_restant_au_premier():
    assert repartir(1000, 3) == [334, 333, 333]
    assert repartir(3000, 3) == [1000, 1000, 1000]
    assert repartir(101, 2) == [51, 50]
    assert repartir(1, 3) == [1, 0, 0]


def test_somme_des_soldes_vaut_toujours_zero(conn):
    ajouter(conn, 1000, [ALICE, BOB, CHLOE], payeur=ALICE)
    ajouter(conn, 777, [BOB, CHLOE], payeur=BOB)
    ajouter(conn, 101, [ALICE, CHLOE], payeur=CHLOE)
    assert sum(calculer_soldes(conn, 1).values()) == 0


@pytest.mark.parametrize("date", [DEBUT, FIN])
def test_bornes_du_sejour_acceptees(date):
    assert valider_depense("Courses", 500, date, [ALICE], DEBUT, FIN) == []


@pytest.mark.parametrize("date", ["2026-06-30", "2026-07-09"])
def test_dates_hors_bornes_refusees(date):
    assert valider_depense("Courses", 500, date, [ALICE], DEBUT, FIN) != []


def test_depense_sans_participant_refusee():
    erreurs = valider_depense("Courses", 500, "2026-07-02", [], DEBUT, FIN)
    assert erreurs == ["Au moins un participant est requis."]


def test_libelle_vide_refuse():
    erreurs = valider_depense("   ", 500, "2026-07-02", [ALICE], DEBUT, FIN)
    assert erreurs == ["Le libellé est obligatoire."]


def test_depense_valide_sans_erreur():
    assert valider_depense("Courses", 3000, "2026-07-02", [ALICE, BOB], DEBUT, FIN) == []


def test_suppression_depense_remet_soldes_a_zero(conn):
    ajouter(conn, 3000, [ALICE, BOB, CHLOE])
    conn.execute("DELETE FROM depenses")
    conn.execute("DELETE FROM participants")
    assert calculer_soldes(conn, 1) == {ALICE: 0, BOB: 0, CHLOE: 0}


# --- Membres ---


def test_nom_de_membre_vide_refuse():
    assert valider_nom_membre("   ", ["Alice"]) == ["Le nom est obligatoire."]


def test_nom_de_membre_en_double_refuse():
    assert valider_nom_membre(" alice ", ["Alice", "Bob"]) == ["« alice » est déjà membre du groupe."]


def test_nom_de_membre_valide_accepte():
    assert valider_nom_membre("Chloé", ["Alice", "Bob"]) == []


def test_stats_membres_comptent_paiements_et_participations(conn):
    ajouter(conn, 3000, [ALICE, BOB, CHLOE], payeur=ALICE)
    ajouter(conn, 1000, [ALICE, BOB], payeur=BOB)
    stats = stats_membres(conn, 1)
    assert stats[ALICE] == {"paye": 3000, "nb_payees": 1, "nb_participations": 2}
    assert stats[BOB] == {"paye": 1000, "nb_payees": 1, "nb_participations": 2}
    assert stats[CHLOE] == {"paye": 0, "nb_payees": 0, "nb_participations": 1}


def test_membre_sans_depense_est_supprimable(conn):
    stats = stats_membres(conn, 1)
    assert raisons_de_ne_pas_supprimer(stats[CHLOE]) == []


def test_membre_rattache_a_une_depense_nest_pas_supprimable(conn):
    ajouter(conn, 3000, [ALICE, BOB, CHLOE], payeur=ALICE)
    stats = stats_membres(conn, 1)
    assert raisons_de_ne_pas_supprimer(stats[ALICE]) == [
        "1 dépense(s) payée(s)",
        "1 participation(s)",
    ]
    assert raisons_de_ne_pas_supprimer(stats[CHLOE]) == ["1 participation(s)"]
