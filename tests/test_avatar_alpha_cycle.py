from app.saas.avatar_alpha import AlphaCycleCache


def test_alpha_cycle_matches_musetalk_ping_pong_sequence() -> None:
    assert [AlphaCycleCache.cycle_index(4, i) for i in range(12)] == [0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3]


def test_single_frame_alpha_is_stable() -> None:
    assert [AlphaCycleCache.cycle_index(1, i) for i in range(5)] == [0, 0, 0, 0, 0]
