"""CG-16: extra exact-age and fail-closed tests for viewing decision mutants.

Test-only: does not alter any rule for levels, programs or watching.
A test must be shown failing against an actual mutant before its mutant
is counted as killed; the current branch mutation run is NOT RUN here.
"""

import pytest

from app.titles import Judged
from app.viewing import Level, Reach, Viewer


@pytest.mark.parametrize(
    ("tv", "age_limit"),
    [(False, 0), (False, 10), (False, 13), (False, 17),
     (True, 0), (True, 7), (True, 14), (True, 17)],
)
def test_age_cutoff_includes_exact_rating_but_excludes_next_age(tv, age_limit):
    level = Level(100, "Exact boundary", age_limit, age_limit, False, None)
    permitted = Judged(tv, age_limit, "m1", True)
    too_old = Judged(tv, age_limit + 1, "m1", True)
    assert level.allows(permitted) is True
    assert level.allows(too_old) is False


@pytest.mark.parametrize("age_limit", [0, 7, 13, 17])
def test_station_reach_at_exact_limit_is_eligible_and_above_is_not(age_limit):
    level = Level(100, "Exact boundary", age_limit, age_limit, False, None)
    matching = Reach(
        known=True, movie_age=age_limit, tv_age=age_limit,
        libraries=frozenset({"m1"}),
    )
    too_old_movie = Reach(
        known=True, movie_age=age_limit + 1, tv_age=age_limit,
        libraries=frozenset({"m1"}),
    )
    too_old_show = Reach(
        known=True, movie_age=age_limit, tv_age=age_limit + 1,
        libraries=frozenset({"m1"}),
    )
    assert level.allows_reach(matching) is True
    assert level.allows_reach(too_old_movie) is False
    assert level.allows_reach(too_old_show) is False


def test_unknown_rating_never_implicitly_crosses_age_boundary():
    restricted = Level(100, "Restricted", 13, 13, False, None)
    assert restricted.allows(Judged(False, None, "m1", False)) is False
    assert restricted.allows(Judged(False, None, "m1", True)) is False
    assert restricted.allows_reach(Reach(known=False)) is False


def test_a_hidden_episode_overrides_even_unrestricted_viewer():
    unrestricted = Level(101, "Unrestricted", None, None, True, None)
    viewer = Viewer(
        unrestricted, everything=True, hidden=frozenset({"ep-1"}),
    )
    judged = Judged(True, 0, "m1", True, own_key="ep-1")
    assert viewer.sees(judged) is False
    assert viewer.sees(Judged(True, 0, "m1", True, own_key="ep-2")) is True


@pytest.mark.parametrize("ready", [None, False])
def test_mandatory_clean_audio_stays_fail_closed(ready):
    unrestricted = Level(101, "Unrestricted", None, None, True, None)
    viewer = Viewer(unrestricted, everything=True, needs_clean=True)
    assert viewer.sees(Judged(False, 0, "m1", True, clean=ready)) is False
    assert viewer.sees(Judged(False, 0, "m1", True, clean=True)) is True
