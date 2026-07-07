"""Badge-2 chain: SS Ticket obtained from Bill at the Sea Cottage, unattended.

Regenerate: python -m dexbot.story visit_bill m7_bridge.ss1 m7_ss_ticket.ss1
"""

from dexbot import PROJECT_ROOT


def test_ss_ticket_obtained():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_ss_ticket.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import get_event_flag

    assert get_event_flag("GOT_SS_TICKET")
    assert get_event_flag("HELPED_BILL_IN_SEA_COTTAGE")
    assert get_item_bag().quantity_of(get_item_by_name("S.S. Ticket")) >= 1
