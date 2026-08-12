"""Tests for the user-controlled course visibility filter."""

import pytest

from canvas_mcp.core.config import reset_config
from canvas_mcp.core.course_filter import (
    filter_courses,
    format_hidden_note,
    is_course_id_visible,
    is_course_visible,
)


def _course(course_id, code, name=""):
    return {"id": course_id, "course_code": code, "name": name or code}


@pytest.fixture
def configure(monkeypatch):
    """Set the two filter env vars and rebuild the config singleton."""

    def _set(include="", exclude=""):
        monkeypatch.setenv("CANVAS_COURSE_INCLUDE", include)
        monkeypatch.setenv("CANVAS_COURSE_EXCLUDE", exclude)
        reset_config()

    return _set


# --- the real NUS enrolment list, verified against canvas.nus.edu.sg ---------
# why: this is the fixture that matters. CS1101S (a TA enrolment) and
#      2627-NUSWS (a Non-Academic term) are the two courses every plausible
#      heuristic — filter by role, by term, by course level — would wrongly
#      drop. They are kept here precisely to pin that down.
NUS_COURSES = [
    _course(99835, "2627-NUSWS", "AY26/27 NUS Wind Symphony"),
    _course(93550, "CFA3101A", "CFA3101A Performing Arts in Practice (Music) 3A [2610]"),
    _course(93601, "CP3209", "CP3209 Undergraduate Research Project in Computing [2610]"),
    _course(93670, "CS1101S", "CS1101S Programming Methodology [2610]"),
    _course(93797, "CS3219", "CS3219 Software Design and Architecture [2610]"),
    _course(93802, "CS3230", "CS3230 Design and Analysis of Algorithms [2610]"),
    _course(95869, "NEP3001", "NEP3001 Impact Experience Project [2610]"),
    _course(98345, "NHS2108", "NHS2108 Morality: Fact or Fiction? [2610]"),
    _course(95819, "NST2030", "NST2030 Quantum Computation [2610]"),
    _course(81917, "CP2106", "Orbital 25"),
    _course(40631, "RC1010A", "RC1010A Refresher for A Culture of Respect and Consent"),
    _course(41924, "SOCT101", "SOCT101 SoC Teaching Workshop"),
    _course(40535, "NUSC_SP", "Special Programmes"),
    _course(40630, "THE1001/RC1000A", "THE1001/RC1000A A Culture of Respect and Consent"),
    _course(40629, "THE1002/SE1000", "THE1002/SE1000 Student Essentials"),
    _course(51188, "TPC", "Travel Preparedness Course"),
]

SHIPPED_EXCLUDE = "CP2106,RC1010A,SOCT101,NUSC_SP,THE1001/RC1000A,THE1002/SE1000,TPC"


# --- the fork's key regression guard ----------------------------------------


def test_empty_config_is_a_no_op(configure):
    """Default path must behave exactly as upstream did: nothing filtered."""
    configure()
    visible, hidden = filter_courses(NUS_COURSES)
    assert visible == NUS_COURSES
    assert hidden == []
    assert format_hidden_note(hidden) == ""


# --- entry shapes -----------------------------------------------------------


def test_digit_entry_matches_canvas_id(configure):
    configure(exclude="93670")
    assert not is_course_visible(_course(93670, "CS1101S"))
    assert is_course_visible(_course(93797, "CS3219"))


def test_digit_entry_does_not_match_a_course_code_that_looks_numeric(configure):
    """A numeric entry is an id, never a code — otherwise ids and codes collide."""
    configure(exclude="12345")
    assert is_course_visible(_course(999, "12345", "Oddly named course"))


def test_exact_code_entry_matches_case_insensitively(configure):
    configure(exclude="cs3219")
    assert not is_course_visible(_course(93797, "CS3219"))


def test_exact_code_entry_does_not_match_a_prefix(configure):
    """Exact means exact: CS321 must not silently take out CS3219."""
    configure(exclude="CS321")
    assert is_course_visible(_course(93797, "CS3219"))


def test_code_with_slash_is_treated_as_an_exact_code(configure):
    """'/' is not a glob metacharacter, so these stay exact matches."""
    configure(exclude="THE1001/RC1000A")
    assert not is_course_visible(_course(40630, "THE1001/RC1000A"))


def test_glob_matches_course_code(configure):
    configure(exclude="CS32*")
    assert not is_course_visible(_course(93797, "CS3219"))
    assert not is_course_visible(_course(93802, "CS3230"))
    assert is_course_visible(_course(93670, "CS1101S"))


def test_glob_matches_course_name(configure):
    configure(exclude="*orientation*")
    assert not is_course_visible(_course(1, "XYZ999", "FoS Freshmen Orientation Hub"))
    assert is_course_visible(_course(2, "CS3219", "Software Design and Architecture"))


def test_glob_is_case_insensitive(configure):
    configure(exclude="*ORIENTATION*")
    assert not is_course_visible(_course(1, "XYZ999", "Freshmen orientation hub"))


def test_question_mark_glob_matches_single_character(configure):
    configure(exclude="CS321?")
    assert not is_course_visible(_course(93797, "CS3219"))
    assert is_course_visible(_course(1, "CS32199", "Longer code"))


# --- include / exclude interaction ------------------------------------------


def test_include_acts_as_an_allow_list(configure):
    configure(include="CS3219,CS3230")
    visible, hidden = filter_courses(NUS_COURSES)
    assert [c["course_code"] for c in visible] == ["CS3219", "CS3230"]
    assert len(hidden) == 14


def test_include_glob_allow_list(configure):
    """The '[2610]' suffix makes a viable 'this semester only' allow-list."""
    configure(include="*[[]2610]*")
    visible, _ = filter_courses(NUS_COURSES)
    assert all("[2610]" in c["name"] for c in visible)
    assert len(visible) == 8


def test_exclude_wins_when_both_lists_match(configure):
    configure(include="CS3219", exclude="CS3219")
    assert not is_course_visible(_course(93797, "CS3219"))


# --- real-data case ---------------------------------------------------------


def test_shipped_default_keeps_exactly_the_nine_essential_courses(configure):
    configure(exclude=SHIPPED_EXCLUDE)
    visible, hidden = filter_courses(NUS_COURSES)

    assert [c["course_code"] for c in visible] == [
        "2627-NUSWS",
        "CFA3101A",
        "CP3209",
        "CS1101S",
        "CS3219",
        "CS3230",
        "NEP3001",
        "NHS2108",
        "NST2030",
    ]
    assert len(hidden) == 7


def test_shipped_default_keeps_the_two_courses_heuristics_would_drop(configure):
    """CS1101S is a TA enrolment; Wind Symphony is a Non-Academic term."""
    configure(exclude=SHIPPED_EXCLUDE)
    assert is_course_visible(_course(93670, "CS1101S"))
    assert is_course_visible(_course(99835, "2627-NUSWS", "AY26/27 NUS Wind Symphony"))


def test_filter_preserves_input_order(configure):
    configure(exclude="CP2106")
    visible, _ = filter_courses(NUS_COURSES)
    assert visible == [c for c in NUS_COURSES if c["course_code"] != "CP2106"]


# --- the hidden note --------------------------------------------------------


def test_hidden_note_names_the_hidden_courses(configure):
    configure(exclude=SHIPPED_EXCLUDE)
    _, hidden = filter_courses(NUS_COURSES)
    note = format_hidden_note(hidden)

    assert "7 course(s) hidden" in note
    assert "CANVAS_COURSE_EXCLUDE" in note
    # why: the names are the point — without them an agent reading a listing
    #      concludes the user is not enrolled and says so.
    for code in ("CP2106", "RC1010A", "TPC"):
        assert code in note
    assert "still reachable" in note


def test_hidden_note_is_empty_when_nothing_hidden(configure):
    configure()
    assert format_hidden_note([]) == ""


# --- id-only checks (todo items) --------------------------------------------


def test_id_only_check_honours_digit_entries(configure):
    configure(exclude="81917")
    assert not is_course_id_visible(81917)
    assert is_course_id_visible(93797)


def test_id_only_check_keeps_unidentifiable_items(configure):
    """A todo we cannot attribute is kept: hiding real work beats hiding noise."""
    configure(exclude=SHIPPED_EXCLUDE)
    assert is_course_id_visible(None)
    assert is_course_id_visible("")


def test_id_only_check_cannot_apply_code_entries(configure):
    """Code entries need a course record, so they do not hide by id alone."""
    configure(exclude="CP2106")
    assert is_course_id_visible(81917)
