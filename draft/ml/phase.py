# draft/encoding/phase.py

def get_draft_phase(sequence_number: int) -> str:
    if sequence_number < 6:
        return "EARLY"
    elif sequence_number < 14:
        return "MID"
    return "LATE"
