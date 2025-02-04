#!/bin/python3
"""
This script is used in pre-commit hooks as well as the CircleCI tests to make
sure that we fail out if we don't meet the minimum percentage threshold we
define for coverage or linting. It is meant to be self contained.
"""

import sys
import argparse
import json
import git
import requests
import xml.etree.ElementTree as ET

MIN_COVERAGE_SCORE = 0.8
MIN_LINT_SCORE = 0.9
PYPI_XML_URL = "https://pypi.org/rss/project/terrasnek/releases.xml"


def get_coverage_score():
    """
    Get the coverage score from the coverage output, return it.
    """
    json_coverage = None
    with open("./coverage.tfc.json", "r") as infile:
        json_coverage = json.loads(infile.read())
    percent_covered = json_coverage["totals"]["percent_covered"] / 100
    return percent_covered

def get_lint_score():
    """
    Get the lint score from the pylint output, return it.
    """
    lint_results = ""

    with open("./lint_output.txt", "r") as infile:
        lint_results = infile.read()

    lint_results_list = [i for i in lint_results.split("\n") if i]
    score_line = lint_results_list[-1]
    score = float(score_line.replace("Your code has been rated at ", "")\
        .split(" ")[0].split("/")[0]) / 10

    return score

def get_pypi_latest_published_version():
    """
    Get the most recent published version on PyPi.

    NOTE: this is a brittle function as we grab the first version from the XML.
    """
    req = requests.get(PYPI_XML_URL)
    tree = ET.fromstring(req.content)
    latest_published_version = None

    for i, item in enumerate(tree.iter("title")):
        # The second "title" in the XML is our latest version, this is not good code.
        if i == 1:
            latest_published_version = item.text
            break

    return latest_published_version


def get_local_versions():
    """
    Get the release version numbers from all the important local files.
    """
    changelog_lines = []
    changelog_version = None

    setup_lines = []
    pypi_config_version = None

    conf_lines = []
    docs_version = None

    with open("./CHANGELOG.md", "r") as infile:
        changelog_lines = infile.readlines()

    for line in changelog_lines:
        if "##" in line:
            changelog_version = \
                line[line.find("[")+1:line.find("]")].strip()
            break

    with open("./setup.py", "r") as infile:
        setup_lines = infile.readlines()
        for line in setup_lines:
            if "version" in line:
                pypi_config_version = line.split('"')[1].strip()
                break

    with open("./docs/conf.py", "r") as infile:
        conf_lines = infile.readlines()
        for line in conf_lines:
            if "release" in line:
                docs_version = line.split("'")[1].strip()
                break

    return changelog_version, pypi_config_version, docs_version


def has_staged_or_modified_files():
    """
    Check to see if the local git repo has staged or modified files.

    Returns true if it does.
    """
    repo = git.Repo()
    count_modified_files = len(repo.index.diff(None))
    count_staged_files = len(repo.index.diff("HEAD"))
    return (count_modified_files > 0) or (count_staged_files > 0)


def main():
    """
    Retrieve the coverage and lint scores, and compare them to the tolerable
    thresholds. Make sure all of the relevant files in this project reflect the
    same project version.
    """
    parser = argparse.ArgumentParser(description="Run some sanity checks for contributing and releasing.")
    parser.add_argument('--release-check', dest="release_check", action="store_true", \
        help="If set, run the release checker.")
    args = parser.parse_args()

    coverage_score = get_coverage_score()
    lint_score = get_lint_score()
    changelog_version, pypi_config_version, docs_version = get_local_versions()

    meets_coverage = coverage_score >= MIN_COVERAGE_SCORE
    meets_lint = lint_score >= MIN_LINT_SCORE
    version_match = changelog_version == pypi_config_version == docs_version

    # TODO: check all implementation files have docs?

    err_msg_list = []
    if not meets_coverage:
        err_msg_list.append(\
            f"The coverage score {coverage_score} \
                does not meet the coverage threshold {MIN_COVERAGE_SCORE}.")

    if not meets_lint:
        err_msg_list.append(\
            f"The lint score {lint_score} does not meet the lint threshold {MIN_LINT_SCORE}.")

    latest_published_version = None
    if args.release_check:
        # Check that the version in the important files is not already present in PyPi.
        latest_published_version = get_pypi_latest_published_version()

        if latest_published_version is None:
            pass

        if not version_match:
            err_msg_list.append(\
                f"The versions do not match across the important files (CHANGELOG.md, setup.py, docs/conf.py).")

        if latest_published_version >= changelog_version:
            err_msg_list.append(\
                f"The latest version in CHANGELOG.md is greater or equal to the latest in PyPi, do not release.")

        if latest_published_version >= pypi_config_version:
            err_msg_list.append(\
                f"The latest version in the PyPi config is greater or equal to the latest in PyPi, do not release.")

        # TODO: handle bugfix release numbers with lower numbers than the latest minor or major release)
        if latest_published_version >= docs_version:
            err_msg_list.append(\
                f"The latest version in docs config is greater or equal to the latest in PyPi, do not release.")

        if has_staged_or_modified_files():
            err_msg_list.append(\
                f"No releasing the project with staged or modified files in the git repo.")

    if err_msg_list:
        print("\n".join(err_msg_list), "\nExiting.")
        sys.exit(1)
    else:
        print(f"Coverage score meets the threshold of {MIN_COVERAGE_SCORE * 100}% at {round(coverage_score * 100, 2)}%.")
        print(f"Lint score meets the threshold of {MIN_LINT_SCORE * 100}% at {round(lint_score * 100, 2)}%.")
        print("All of the versions match in the important files (CHANGELOG.md, setup.py, docs/conf.py).")
        if latest_published_version is not None and \
            latest_published_version < changelog_version and \
            latest_published_version < pypi_config_version and \
                latest_published_version < docs_version:
                    print("All versions locally are greater than published PyPi modules, good to release.")

if __name__ == "__main__":
    main()
