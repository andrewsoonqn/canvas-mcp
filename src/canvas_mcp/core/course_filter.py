"""User-controlled course visibility filter for listings.

A student's Canvas enrolment list is padded with institutional shells —
compliance modules, orientation courses, faculty-wide announcement shells —
that they never read. They crowd out real modules in every listing, and at NUS
they were 7 of 16 active courses.

Scope is deliberately narrow: this filter is **decluttering, not access
control**. An excluded course is omitted from listings, but stays fully
reachable by id or course code, and the course-code cache is never filtered.
That is the whole difference between this and a boundary, and it is a design
decision rather than an oversight — do not "fix" it by filtering the cache in
core/cache.py, which would silently convert this into an access mechanism it
was never reviewed as.

Because the filter can hide something the user wanted, every caller is expected
to surface *what* was hidden (see ``format_hidden_note``) rather than dropping
courses silently. A vanished course must never be indistinguishable from a
Canvas enrolment problem.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from .config import get_config

# why: globs are matched with fnmatch rather than regex so that ordinary course
#      codes stay literal. `CS2103T` and `THE1001/RC1000A` contain no fnmatch
#      metacharacter, so an exact code can never accidentally behave as a
#      pattern — which a regex dialect would not guarantee.
_GLOB_CHARS = ("*", "?", "[")


def _entry_matches(entry: str, course: dict[str, Any]) -> bool:
    """Test one config entry against one course dict.

    The entry's shape selects the rule:

    * all digits -> Canvas course id
    * contains a glob metacharacter -> case-insensitive glob, against both
      course code and course name
    * anything else -> case-insensitive exact course-code match
    """
    if not entry:
        return False

    if entry.isdigit():
        # note: compared as strings because Canvas ids arrive as int from the
        #       API but as str from the code cache.
        return str(course.get("id", "")) == entry

    code = str(course.get("course_code") or "")
    name = str(course.get("name") or "")

    if any(ch in entry for ch in _GLOB_CHARS):
        pattern = entry.lower()
        # why: globs test the name as well as the code because the noise being
        #      removed is usually recognisable by name ("...Orientation Hub")
        #      while real modules are recognisable by code ("CS21*").
        return fnmatch(code.lower(), pattern) or fnmatch(name.lower(), pattern)

    # why: case-insensitive because Canvas returns codes in mixed case across
    #      fields, and a config that silently does nothing because of casing is
    #      the worst possible failure here.
    return code.lower() == entry.lower()


def is_course_visible(course: dict[str, Any]) -> bool:
    """Whether a course survives the configured include/exclude lists."""
    config = get_config()
    include = config.canvas_course_include
    exclude = config.canvas_course_exclude

    if include and not any(_entry_matches(e, course) for e in include):
        return False

    # why: exclude is evaluated last so it wins when both lists match the same
    #      course. When the two lists contradict each other the config is
    #      already wrong, and the narrower result is the predictable one.
    return not any(_entry_matches(e, course) for e in exclude)


def filter_courses(
    courses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split courses into (visible, hidden), preserving order.

    Returns the hidden courses rather than just a count so callers can name
    them to the user.
    """
    visible: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for course in courses:
        (visible if is_course_visible(course) else hidden).append(course)
    return visible, hidden


def is_course_id_visible(course_id: Any) -> bool:
    """Visibility check when only an id is known (todo items carry no course).

    Digit and glob entries that could match an id are honoured; code-based
    entries cannot be evaluated without a course record, so they do not hide
    anything here.
    """
    if course_id in (None, ""):
        return True
    return is_course_visible({"id": course_id, "course_code": "", "name": ""})


def format_hidden_note(hidden: list[dict[str, Any]]) -> str:
    """One-line note naming the hidden courses, or "" when nothing was hidden.

    why: naming them, rather than only counting, keeps a hidden course usable in
         conversation. Without the names an agent that consults a listing will
         conclude the user is not enrolled and say so confidently — the filter
         would be turning decluttering into misinformation.
    """
    if not hidden:
        return ""

    labels = [
        str(c.get("course_code") or c.get("name") or c.get("id") or "?")
        for c in hidden
    ]
    config = get_config()
    sources = []
    if config.canvas_course_exclude:
        sources.append("CANVAS_COURSE_EXCLUDE")
    if config.canvas_course_include:
        sources.append("CANVAS_COURSE_INCLUDE")
    source = " / ".join(sources) or "course filter"

    return (
        f"({len(hidden)} course(s) hidden by {source}: {', '.join(labels)} — "
        f"still reachable by code or id)"
    )
