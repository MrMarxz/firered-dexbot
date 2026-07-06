"""M2 acceptance: spot-check the generated knowledge base against documented facts.

Expected values come from Bulbapedia's FireRed pages (encounter rates, gym parties),
independent of the code that generated the KB.
"""

import json

import pytest

from dexbot import PROJECT_ROOT, POKEBOT_ROOT

DATA = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def encounters():
    return json.loads((DATA / "encounters.json").read_text())


def by_name(encounters, name):
    return next(v for v in encounters.values() if v["map_name"] == name)


def rate_for(slots, species):
    return sum(e["encounter_rate"] for e in slots if e["species_name"] == species)


def test_pikachu_in_viridian_forest(encounters):
    slots = by_name(encounters, "VIRIDIAN_FOREST")["land_encounters"]
    assert rate_for(slots, "Pikachu") == 5  # Bulbapedia: 5%
    assert rate_for(slots, "Caterpie") == 40  # FireRed version bias


def test_abra_rates_on_route_24(encounters):
    slots = by_name(encounters, "ROUTE24")["land_encounters"]
    assert rate_for(slots, "Abra") == 15  # Bulbapedia: 15%
    levels = [e for e in slots if e["species_name"] == "Abra"]
    assert all(8 <= e["min_level"] <= e["max_level"] <= 14 for e in levels)


def test_route_4_surf_and_fishing_present(encounters):
    route4 = by_name(encounters, "ROUTE4")
    assert route4["fishing_encounter_rate"] > 0
    assert rate_for(route4["old_rod_encounters"], "Magikarp") == 100  # old rod is always Magikarp


def test_brocks_party():
    trainers = json.loads((DATA / "trainers.json").read_text())
    brock = next(t for t in trainers.values() if t["name"] == "BROCK")
    assert [(m["species"], m["level"]) for m in brock["party"]] == [("Geodude", 12), ("Onix", 14)]


def test_tmhm_moves():
    tmhm = json.loads((DATA / "tmhm.json").read_text())
    assert tmhm["HM01"]["move"] == "Cut"
    assert tmhm["HM03"]["move"] == "Surf"
    assert tmhm["HM04"]["move"] == "Strength"
    assert tmhm["TM26"]["move"] == "Earthquake"
    assert len([k for k in tmhm if k.startswith("TM")]) == 50


def test_species_data_squirtle_line():
    species = json.loads((POKEBOT_ROOT / "modules/data/species.json").read_text())
    squirtle = next(s for s in species if s["name"] == "Squirtle")
    assert squirtle["catch_rate"] == 45
    assert squirtle["evolutions"][0] == {"method": "level", "method_param": 16, "target_species": 8}  # Wartortle


def test_dependency_graph_is_acyclic_and_closed():
    deps = json.loads((DATA / "dependencies.json").read_text())
    objectives = deps["objectives"]

    def resolve(node, stack=()):
        assert node not in stack, f"cycle: {stack} -> {node}"
        for requirement in objectives[node]["requires"]:
            if requirement in objectives:
                resolve(requirement, (*stack, node))
            else:
                assert requirement.endswith("_GET"), f"unknown requirement {requirement!r} of {node}"

    for name in objectives:
        resolve(name)
