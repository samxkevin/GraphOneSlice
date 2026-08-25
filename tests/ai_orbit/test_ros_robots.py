from datetime import datetime, timezone

from src.ai_orbit.adapters.ros_robots import RosRobotsCatalogAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def _robot_markdown():
    return """---
layout: post
title: "TurtleBot2"
date: 2016-08-07 01:53:39
description: 'The TurtleBot2'
main-class: 'ground'
tags:
- "ground"
- "mobile base"
website: http://www.turtlebot.com
wiki_homepage: http://wiki.ros.org/Robots/TurtleBot
introduction: "TurtleBot is a low-cost, personal robot kit with open-source software"
---

TurtleBot is a low-cost robot kit that can drive around your house and see in 3D.
"""


def test_ros_robots_front_matter_parser_preserves_robot_identity_fields():
    adapter = RosRobotsCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))
    front_matter, body = adapter._parse_front_matter(_robot_markdown())
    assert front_matter["title"] == "TurtleBot2"
    assert front_matter["main-class"] == "ground"
    assert front_matter["website"] == "http://www.turtlebot.com"
    assert front_matter["wiki_homepage"] == "http://wiki.ros.org/Robots/TurtleBot"
    assert front_matter["tags"] == ["ground", "mobile base"]
    assert "low-cost robot kit" in body


def test_ros_robots_record_uses_catalog_metadata_without_inventing_provider():
    adapter = RosRobotsCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))
    front_matter, body = adapter._parse_front_matter(_robot_markdown())
    row = {
        "front_matter": front_matter,
        "body": body,
        "path": "_posts/2016-08-07-turtlebot.md",
        "slug": "turtlebot",
        "html_url": "https://github.com/ros-infrastructure/robots.ros.org/blob/gh-pages/_posts/2016-08-07-turtlebot.md",
        "api_url": "https://api.github.com/repos/ros-infrastructure/robots.ros.org/contents/_posts/2016-08-07-turtlebot.md?ref=gh-pages",
    }
    assert adapter._is_candidate_robot(row)
    record = adapter._record_from_row(row, fetched_at=datetime.now(timezone.utc))
    assert record is not None
    assert record.entity_type == "robot"
    assert record.categories == ["Robots"]
    assert record.url == "http://www.turtlebot.com/"
    assert record.source_url == "https://api.github.com/repos/ros-infrastructure/robots.ros.org/contents/_posts/2016-08-07-turtlebot.md?ref=gh-pages"
    robot_metadata = record.metadata["robot"]
    assert robot_metadata["catalog_url"] == "https://robots.ros.org/turtlebot/"
    assert robot_metadata["catalog_posted_at"] == "2016-08-07T01:53:39+00:00"
    assert robot_metadata["robot_class"] == "ground"
    assert robot_metadata["manufacturer"] is None
    assert robot_metadata["provider"] is None
    assert robot_metadata["identity_evidence"]["field"] == "title/introduction"


def test_robot_validation_requires_catalog_url_and_identity_evidence():
    robot = Entity(
        id="robot-1",
        entity_type="robot",
        name="TurtleBot2",
        description="TurtleBot is a low-cost, personal robot kit with open-source software.",
        url="https://robots.ros.org/turtlebot/",
        categories=["Robots"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata={"robot": {"catalog_url": "https://robots.ros.org/turtlebot/", "identity_evidence": {"field": "title"}}},
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:robot",
            observed_fields={"name": "TurtleBot2"},
        ),
    )
    accepted, _relationships, report = validate_outputs([robot], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    missing_metadata = robot.model_copy(update={"id": "robot-2", "metadata": {}})
    accepted, _relationships, report = validate_outputs([missing_metadata], [])
    assert accepted == []
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1


def test_ros_robots_filter_rejects_software_support_blurbs():
    adapter = RosRobotsCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))
    row = {
        "front_matter": {
            "title": "ABB Manipulators",
            "date": "2016-08-12",
            "introduction": "ROS-Industrial support for ABB manipulators",
            "main-class": "manipulator",
            "wiki_homepage": "http://wiki.ros.org/abb",
            "tags": ["ROS-Industrial", "abb"],
        },
        "body": "This repository is part of the ROS-Industrial program.",
        "path": "_posts/2016-08-12-abb-manipulators.md",
        "slug": "abb-manipulators",
        "html_url": "https://github.com/ros-infrastructure/robots.ros.org/blob/gh-pages/_posts/2016-08-12-abb-manipulators.md",
        "api_url": "https://api.github.com/repos/ros-infrastructure/robots.ros.org/contents/_posts/2016-08-12-abb-manipulators.md?ref=gh-pages",
    }
    assert not adapter._is_candidate_robot(row)
