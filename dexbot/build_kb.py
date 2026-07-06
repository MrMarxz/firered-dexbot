"""M2: generate the knowledge base in data/ from the ROM + upstream pret-derived JSON.

Encounters and trainer parties are read straight out of the verified FireRed 1.0
ROM via pret symbol tables — no hand-copied game facts.

Run:  .venv/bin/python -m dexbot.build_kb
"""

import json
import struct

from dexbot import PROJECT_ROOT, POKEBOT_ROOT
from dexbot.emulator import setup_headless_emulator

DATA_DIR = PROJECT_ROOT / "data"


def dump_encounters(context) -> dict:
    from modules.map import get_wild_encounters_for_map
    from modules.map_data import MapFRLG
    from modules.memory import read_symbol, unpack_uint32

    result = {}
    headers = read_symbol("gWildMonHeaders")
    for index in range(len(headers) // 20):
        group, number = headers[index * 20], headers[index * 20 + 1]
        if group == 0xFF:
            break
        encounters = get_wild_encounters_for_map(group, number)
        if encounters is None:
            continue
        try:
            map_name = MapFRLG((group, number)).name
        except ValueError:
            map_name = f"UNKNOWN_{group}_{number}"
        result[f"{group},{number}"] = {"map_name": map_name, **encounters.to_dict()}
    return result


def dump_trainers(context) -> dict:
    """Decode the full gTrainers table (pret struct Trainer, 0x28 bytes each)."""
    from modules.game import decode_string, get_symbol
    from modules.pokemon import get_species_by_index

    emulator = context.emulator
    address, length = get_symbol("gTrainers")
    trainer_count = length // 0x28
    data = emulator.read_bytes(address, length)

    trainers = {}
    for i in range(trainer_count):
        t = data[i * 0x28 : (i + 1) * 0x28]
        party_flags = t[0]
        name = decode_string(t[4:16])
        party_size = t[0x20]
        party_ptr = struct.unpack("<I", t[0x24:0x28])[0]
        if party_size == 0 or party_ptr == 0:
            continue

        custom_moves = bool(party_flags & 1)
        held_item = bool(party_flags & 2)
        entry_size = 16 if custom_moves else 8
        raw_party = emulator.read_bytes(party_ptr, party_size * entry_size)

        party = []
        for n in range(party_size):
            e = raw_party[n * entry_size : (n + 1) * entry_size]
            iv, level, species_id = struct.unpack("<HBxH", e[:6])
            mon = {
                "species": get_species_by_index(species_id).name,
                "level": level,
                "iv_strength": iv,  # 0-255, scaled to 0-31 IVs in all stats
            }
            offset = 6
            if held_item:
                mon["held_item_id"] = struct.unpack("<H", e[offset : offset + 2])[0]
                offset += 2
            if custom_moves:
                mon["move_ids"] = list(struct.unpack("<4H", e[offset : offset + 8]))
            party.append(mon)

        trainers[i] = {"name": name, "trainer_class": t[1], "party": party}
    return trainers


def dump_tmhm() -> dict:
    items = json.loads((POKEBOT_ROOT / "modules/data/items.json").read_text())
    moves = json.loads((POKEBOT_ROOT / "modules/data/moves.json").read_text())
    move_names = {index: m["name"] for index, m in enumerate(moves)}  # move id == list position
    return {
        item["name"]: {"item_index": item["index"], "move": move_names[item["tm_hm_move_id"]]}
        for item in items
        if item.get("tm_hm_move_id") and item["name"][:2] in ("TM", "HM") and len(item["name"]) == 4
    }


def main() -> None:
    context = setup_headless_emulator(is_test_run=True)
    # gWildMonHeaders points into ROM; no save needed, fresh boot is fine.

    DATA_DIR.mkdir(exist_ok=True)
    encounters = dump_encounters(context)
    (DATA_DIR / "encounters.json").write_text(json.dumps(encounters, indent=1) + "\n")
    trainers = dump_trainers(context)
    (DATA_DIR / "trainers.json").write_text(json.dumps(trainers, indent=1) + "\n")
    tmhm = dump_tmhm()
    (DATA_DIR / "tmhm.json").write_text(json.dumps(tmhm, indent=1) + "\n")

    print(f"encounters: {len(encounters)} maps, trainers: {len(trainers)}, TM/HM: {len(tmhm)}")


if __name__ == "__main__":
    main()
