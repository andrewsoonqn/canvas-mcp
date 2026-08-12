"""Regression guards for the course filter inside list_courses.

The load-bearing one is test_cache_is_populated_from_unfiltered_courses.
The filter is decluttering, not access control, and the only thing keeping
that true is that the course-code cache is refreshed from the *unfiltered*
list. A refactor that moves the filter above the cache refresh would silently
convert this feature into an access boundary it was never reviewed as, and no
other test would notice.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.cache import (
    course_code_to_id_cache,
    id_to_course_code_cache,
)
from canvas_mcp.core.config import reset_config
from canvas_mcp.tools.courses import register_course_tools

COURSES = [
    {"id": 93797, "course_code": "CS3219", "name": "Software Design [2610]"},
    {"id": 93802, "course_code": "CS3230", "name": "Algorithms [2610]"},
    {"id": 81917, "course_code": "CP2106", "name": "Orbital 25"},
    {"id": 51188, "course_code": "TPC", "name": "Travel Preparedness Course"},
]


@pytest.fixture
def run_list_courses(monkeypatch):
    async def _run(exclude=""):
        monkeypatch.setenv("CANVAS_COURSE_EXCLUDE", exclude)
        monkeypatch.setenv("CANVAS_COURSE_INCLUDE", "")
        reset_config()
        course_code_to_id_cache.clear()
        id_to_course_code_cache.clear()

        mcp = FastMCP("test")
        with patch(
            "canvas_mcp.tools.courses.fetch_all_paginated_results",
            new=AsyncMock(return_value=list(COURSES)),
        ):
            register_course_tools(mcp)
            tool = await mcp.get_tool("list_courses")
            result = await tool.run({})
        return str(result.content[0].text)

    return _run


async def test_cache_is_populated_from_unfiltered_courses(run_list_courses):
    """Excluded courses must stay resolvable by code — the cosmetic guarantee."""
    output = await run_list_courses(exclude="CP2106,TPC")

    assert "CP2106" not in output.split("hidden by")[0]
    # why: the whole point. Filtered out of the listing, still in the cache.
    assert course_code_to_id_cache["CP2106"] == "81917"
    assert course_code_to_id_cache["TPC"] == "51188"
    assert id_to_course_code_cache["81917"] == "CP2106"


async def test_excluded_courses_are_omitted_from_the_listing(run_list_courses):
    output = await run_list_courses(exclude="CP2106,TPC")
    listing = output.split("hidden by")[0]

    assert "CS3219" in listing
    assert "CS3230" in listing
    assert "Code: CP2106" not in listing
    assert "Code: TPC" not in listing


async def test_footer_names_the_hidden_courses(run_list_courses):
    output = await run_list_courses(exclude="CP2106,TPC")

    assert "2 course(s) hidden" in output
    assert "CP2106" in output
    assert "TPC" in output
    assert "still reachable" in output


async def test_empty_config_lists_everything_without_a_footer(run_list_courses):
    """The fork's default path must be indistinguishable from upstream."""
    output = await run_list_courses(exclude="")

    for code in ("CS3219", "CS3230", "CP2106", "TPC"):
        assert f"Code: {code}" in output
    assert "hidden" not in output


async def test_filtering_everything_explains_itself(run_list_courses):
    """All-filtered must not read as 'you have no courses'."""
    output = await run_list_courses(exclude="*")

    assert "filtered out" in output
    assert "4 course(s) hidden" in output
