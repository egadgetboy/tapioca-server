"""The one viewing decision's rules, each pinned by a test of its own: the
changes a bug could make that mutation testing (tools/mutate.py, the plan's
release gate, DL369) found no test caught on its first run, October 27."""

from __future__ import annotations

from app.db import Database
from app.titles import Judged, Titles
from app.viewing import EVERYONE, Blocks, Level, Reach, Viewer, Viewing

FOLDERS = frozenset({"1"})


def kid(**over) -> Level:
    """Movies to PG, shows to TV-Y7, nothing unrated, Media folder 1 only."""
    given = {"movie_age": 10, "tv_age": 7, "unrated": False, "libraries": FOLDERS} | over
    return Level(1, "Kid", **given)


def station(**over) -> Reach:
    """A Station Kid may watch, unless `over` says otherwise."""
    return Reach(**({"known": True, "movie_age": 0, "tv_age": 0, "libraries": FOLDERS} | over))


# A level: movies by the movie limit, shows by the TV limit ---------------------------


def test_a_movie_is_held_to_the_movie_limit_and_a_show_to_the_tv_one():
    teen = Level(1, "Teen", 10, 14, True, None)
    assert teen.allows(Judged(True, 14, "1", True))  # (a show rated TV-14)
    assert not teen.allows(Judged(False, 14, "1", True))  # (a movie for ages 14)
    assert teen.allows(Judged(False, 10, "1", True))
    assert not teen.allows(Judged(True, 17, "1", True))


def test_a_station_whose_ratings_arent_known_yet_is_held_back():
    assert not kid().allows_reach(Reach(known=False))
    assert kid().why_not(Reach(known=False)) == (
        "tapiOca is still asking Plex about the ratings of what it plays"
    )


def test_a_station_from_exactly_the_levels_media_folders_is_allowed():
    assert kid().allows_reach(station())
    assert kid().why_not(station()) is None


# Why a station is hidden: the first reason that applies, in words ---------------------


def test_a_station_from_another_media_folder_says_so():
    assert kid().why_not(station(libraries=frozenset({"1", "2"}))) == (
        "It plays programs from a Media folder Kid doesn’t include"
    )


def test_a_station_with_movies_too_old_names_their_rating():
    assert kid().why_not(station(movie_age=13)) == "It plays movies rated PG-13"


def test_a_station_with_shows_too_old_names_their_rating():
    assert kid().why_not(station(tv_age=14)) == "It plays shows rated TV-14"


def test_a_station_with_unrated_programs_says_so():
    assert kid().why_not(station(movie_unrated=True)) == "It plays programs that aren’t rated"


def test_unrated_programs_are_named_before_a_hidden_genre():
    # (Both hide it from Kid; the reasons are given in the plan's order.)
    horror = kid(blocks=Blocks(genres=("Horror",)))
    reach = station(movie_unrated=True, genres=frozenset({"horror"}))
    assert horror.why_not(reach) == "It plays programs that aren’t rated"


def test_a_station_at_the_limit_isnt_said_to_pass_it():
    # (Its shows are at Kid's TV-Y7, and its movies within PG: what's wrong is
    # what's unrated, never the shows.)
    assert kid().why_not(station(tv_age=7, tv_unrated=True)) == (
        "It plays programs that aren’t rated"
    )


def test_a_hidden_genre_is_named_even_when_unrated_programs_are_allowed():
    horror = kid(unrated=True, blocks=Blocks(genres=("Horror",)))
    reach = station(movie_unrated=True, genres=frozenset({"horror"}))
    assert horror.why_not(reach) == "It plays programs with the genre Horror, which Kid hides"


def test_a_hidden_title_is_named():
    hidden = kid(blocks=Blocks(titles=(("500", "The Long Night"),)))
    assert hidden.why_not(station(titles=frozenset({"500"}))) == (
        "It plays The Long Night, which Kid hides"
    )


# One person: hidden episodes, Clean audio, and an Admin's Stations ------------------


def test_an_episode_hidden_for_someone_is_refused_even_with_no_limits():
    pat = Viewer(EVERYONE.level, everything=True, hidden=frozenset({"301"}))
    assert not pat.sees(Judged(True, 0, "1", True, own_key="301"))
    assert pat.sees(Judged(True, 0, "1", True, own_key="302"))


def test_clean_audio_needed_is_refused_until_its_ready():
    pat = Viewer(EVERYONE.level, everything=True, needs_clean=True)
    assert not pat.sees(Judged(False, 0, "1", True, clean=None))  # (not known: never ready)
    assert not pat.sees(Judged(False, 0, "1", True, clean=False))
    assert pat.sees(Judged(False, 0, "1", True, clean=True))


def test_someone_with_no_limits_sees_everything():
    assert EVERYONE.sees(Judged(False, 18, "9", False))
    assert EVERYONE.sees(Judged(True, None, "", False))


def test_a_station_an_admin_blocked_is_never_seen(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    viewing = Viewing(db, Titles(db))
    limited = Viewer(
        Level(1, "Open", None, None, True, None), everything=False, blocked=frozenset({5})
    )
    assert not viewing.sees_station(limited, 5)


def test_a_station_is_allowed_by_hand_only_for_someone_with_limits(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    viewing = Viewing(db, Titles(db))
    allowed = frozenset({5})
    assert viewing.allowed_by_hand(Viewer(kid(), everything=False, allowed=allowed), 5)
    assert not viewing.allowed_by_hand(Viewer(kid(), everything=False, allowed=allowed), 6)
    assert not viewing.allowed_by_hand(Viewer(EVERYONE.level, everything=True, allowed=allowed), 5)
