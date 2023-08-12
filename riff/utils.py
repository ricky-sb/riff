import json
import pprint
from pathlib import Path

import git
import typer
from git.repo import Repo
from loguru import logger
from unidiff import PatchedFile, PatchSet

from riff.violation import Violation


def split_paths_by_max_len(
    paths: list[Path],
    max_length_sum: int = 4000,
) -> list[list[Path]]:
    """
    Splits a list of Path objects into sublists based on their total length.

    Args:
        paths (List[Path]): A list of Path objects.
        max_length_sum (int): The maximum total length of each sublist. Default is 4000.

    Returns:
        List[List[Path]]: A list of sublists, where each has a maximum total length.
    """
    result: list[list[Path]] = []
    current_list: list[Path] = []
    current_length_sum = 0

    for path in sorted(set(paths), key=lambda x: len(str(x))):
        path_length = len(str(path))
        if path_length >= max_length_sum:
            raise ValueError(f"Path is longer than {max_length_sum}: {path}")
        if current_length_sum + path_length <= max_length_sum:
            current_list.append(path)
            current_length_sum += path_length
        else:  # exceeded max length
            result.append(current_list)
            current_list = [path]
            current_length_sum = path_length
    if current_list:
        result.append(current_list)
    return result


def validate_paths_relative_to_repo(paths: list[Path], repo_path: Path) -> None:
    repo_path = repo_path.resolve()
    for path in paths:
        with logger.catch(
            ValueError,
            level="ERROR",
            message=f"{path} is not relative to {repo_path=}",
            reraise=False,
        ):
            path.absolute().relative_to(repo_path)


def parse_ruff_output(ruff_result_raw: str) -> tuple[Violation, ...]:
    with logger.catch(json.JSONDecodeError, reraise=True):
        raw_violations = json.loads(ruff_result_raw)

    violations = tuple(map(Violation.parse, raw_violations))
    logger.debug(f"parsed {len(violations)} ruff violations")
    return violations


def parse_git_changed_lines(
    base_branch: str,
) -> dict[Path, set[int]]:
    """Returns
    Dict[Path, Tuple[int]]: maps modified files, to the indices of the lines changed.
    """
    3
    def parse_modified_lines(patched_file: PatchedFile) -> set[int]:
        return {
            line.target_line_no
            for hunk in patched_file
            for line in hunk
            if line.is_added and line.value.strip()
        }

    repo = Repo(search_parent_directories=True)
    result = {
        Path(patched_file.path): parse_modified_lines(patched_file)
        for patched_file in PatchSet(
            repo.git.diff(
                base_branch,
                ignore_blank_lines=True,
                ignore_space_at_eol=True,
            ),
        )
    }
    if result:
        logger.debug(f"modified lines:\n{pprint.pformat(result,compact=True)}")
    else:
        repo_path = Path(repo.git_dir).parent.resolve()
        logger.error(
            f"could not find any git-modified lines in {repo_path}: Are the files committed?"  # noqa: E501
        )
    return result


def validate_repo_path() -> None:
    try:
        git.Repo(search_parent_directories=True)
    except git.exc.InvalidGitRepositoryError:
        logger.error(f"Cannot detect repository in {Path().resolve()}")
        raise typer.Exit(1) from None  # no need for whole stack trace
