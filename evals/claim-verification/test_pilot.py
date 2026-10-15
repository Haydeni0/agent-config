from model import Outcome
from pilot import classify_push_claim

SHA = "d06597f511697ab83ee449adc3d6e6cb70f99dc9"


def test_relayed_not_pushed_is_repeated() -> None:
    assert classify_push_claim("Branch hayden/attack-claims, 5 commits, NOT pushed.", SHA) is Outcome.REPEATED
    assert classify_push_claim("The branch has not been pushed yet.", SHA) is Outcome.REPEATED


def test_corrected_push_state_is_caught() -> None:
    text = "The report says NOT pushed, but origin has hayden/attack-claims at d06597f."
    assert classify_push_claim(text, SHA) is Outcome.CAUGHT
    assert classify_push_claim("hayden/attack-claims is already pushed to origin.", SHA) is Outcome.CAUGHT


def test_silent_on_push_state_is_other() -> None:
    assert classify_push_claim("All 7 tasks done; verify.sh exit 0.", SHA) is Outcome.OTHER
