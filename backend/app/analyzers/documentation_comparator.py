"""
Historical Documentation Comparator for DocGuard (Milestone 5).

Compares Markdown documentation files and extracted DocumentationUnit statements
between `base_commit` and `head_commit` to identify:
- Documentation units that remained unchanged while related code changed.
- Documentation units that were modified alongside code changes.
- Documentation units that were added, deleted, or moved/renamed across files.
"""

from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.documentation import DocumentationUnit
from app.schemas.drift import DocumentationFileChange, DocumentationUnitDiff


def compare_documentation_across_commits(
    base_units_by_file: Dict[str, List[DocumentationUnit]],
    head_units_by_file: Dict[str, List[DocumentationUnit]],
    base_raw_by_file: Dict[str, str],
    head_raw_by_file: Dict[str, str],
    git_renamed_docs: Optional[Dict[str, str]] = None,
) -> Tuple[
    List[DocumentationFileChange],
    List[DocumentationUnitDiff],
    Dict[str, DocumentationUnitDiff],
    Dict[str, DocumentationUnitDiff],
]:
    """
    Compare documentation files and extracted units between base and head commits.

    Returns:
        (
            file_changes,
            unit_diffs,
            diff_by_head_unit_id,
            diff_by_base_unit_id,
        )
    """
    renamed_map = dict(git_renamed_docs or {})  # head_path -> base_path
    reverse_renamed = {v: k for k, v in renamed_map.items()}

    base_paths = set(base_units_by_file.keys()) | set(base_raw_by_file.keys())
    head_paths = set(head_units_by_file.keys()) | set(head_raw_by_file.keys())

    # If Git didn't explicitly flag a rename, detect obvious file move/rename when a
    # deleted doc file and an added doc file share >= 75% content similarity
    removed_only = [p for p in base_paths - head_paths if p not in reverse_renamed]
    added_only = [p for p in head_paths - base_paths if p not in renamed_map]
    for h_path in list(added_only):
        h_text = head_raw_by_file.get(h_path, "")
        if not h_text:
            continue
        best_base: Optional[str] = None
        best_ratio = 0.0
        for b_path in removed_only:
            b_text = base_raw_by_file.get(b_path, "")
            if not b_text:
                continue
            ratio = SequenceMatcher(None, b_text, h_text).ratio()
            if ratio >= 0.75 and ratio > best_ratio:
                best_ratio = ratio
                best_base = b_path
        if best_base is not None:
            renamed_map[h_path] = best_base
            reverse_renamed[best_base] = h_path
            removed_only.remove(best_base)
            added_only.remove(h_path)

    file_changes: List[DocumentationFileChange] = []
    unit_diffs: List[DocumentationUnitDiff] = []
    diff_by_head_unit_id: Dict[str, DocumentationUnitDiff] = {}
    diff_by_base_unit_id: Dict[str, DocumentationUnitDiff] = {}

    matched_base_unit_ids: Set[str] = set()
    matched_head_unit_ids: Set[str] = set()

    # 1. Process files present in head (unchanged, modified, renamed, or added)
    for h_path in sorted(head_paths):
        h_units = head_units_by_file.get(h_path, [])
        b_path = renamed_map.get(h_path, h_path if h_path in base_paths else None)

        if b_path is None:
            file_changes.append(
                DocumentationFileChange(
                    file_path=h_path,
                    previous_path=None,
                    change_type="added",
                    base_units_count=0,
                    head_units_count=len(h_units),
                )
            )
            continue

        b_units = base_units_by_file.get(b_path, [])
        b_raw = base_raw_by_file.get(b_path, "")
        h_raw = head_raw_by_file.get(h_path, "")
        is_file_renamed = b_path != h_path

        if is_file_renamed:
            f_change_type = "renamed"
        elif b_raw == h_raw:
            f_change_type = "unchanged"
        else:
            f_change_type = "modified"

        file_changes.append(
            DocumentationFileChange(
                file_path=h_path,
                previous_path=b_path if is_file_renamed else None,
                change_type=f_change_type,
                base_units_count=len(b_units),
                head_units_count=len(h_units),
            )
        )

        # Pair base and head units within (b_path, h_path)
        _pair_units_in_file(
            base_file=b_path,
            head_file=h_path,
            base_units=b_units,
            head_units=h_units,
            is_file_renamed=is_file_renamed,
            matched_base_unit_ids=matched_base_unit_ids,
            matched_head_unit_ids=matched_head_unit_ids,
            unit_diffs=unit_diffs,
            diff_by_head_unit_id=diff_by_head_unit_id,
            diff_by_base_unit_id=diff_by_base_unit_id,
        )

    # 2. Record deleted documentation files
    for b_path in sorted(base_paths):
        if b_path in head_paths or b_path in reverse_renamed:
            continue
        b_units = base_units_by_file.get(b_path, [])
        file_changes.append(
            DocumentationFileChange(
                file_path=b_path,
                previous_path=None,
                change_type="deleted",
                base_units_count=len(b_units),
                head_units_count=0,
            )
        )

    # 3. Cross-file movement detection: check if an unmatched base unit in a deleted/modified
    # file was moved verbatim or nearly verbatim into an added/modified file
    unmatched_base: List[DocumentationUnit] = [
        u
        for b_path in sorted(base_paths)
        for u in base_units_by_file.get(b_path, [])
        if u.unit_id not in matched_base_unit_ids
    ]
    unmatched_head: List[DocumentationUnit] = [
        u
        for h_path in sorted(head_paths)
        for u in head_units_by_file.get(h_path, [])
        if u.unit_id not in matched_head_unit_ids
    ]

    for h_unit in list(unmatched_head):
        h_norm = h_unit.original_text.strip()
        best_b: Optional[DocumentationUnit] = None
        best_score = 0.0
        for b_unit in unmatched_base:
            if b_unit.unit_id in matched_base_unit_ids:
                continue
            b_norm = b_unit.original_text.strip()
            if h_norm == b_norm:
                best_b = b_unit
                best_score = 1.0
                break
            if (
                b_unit.section_heading
                and b_unit.section_heading == h_unit.section_heading
            ):
                ratio = SequenceMatcher(None, b_norm, h_norm).ratio()
                if ratio >= 0.45 and ratio > best_score:
                    best_score = ratio
                    best_b = b_unit

        if best_b is not None:
            matched_base_unit_ids.add(best_b.unit_id)
            matched_head_unit_ids.add(h_unit.unit_id)
            u_change_type = "moved" if best_score == 1.0 else "modified"
            diff_item = DocumentationUnitDiff(
                documentation_file=h_unit.documentation_file,
                previous_file=best_b.documentation_file,
                change_type=u_change_type,
                section_heading=h_unit.section_heading or best_b.section_heading,
                base_unit_id=best_b.unit_id,
                head_unit_id=h_unit.unit_id,
                base_start_line=best_b.start_line,
                base_end_line=best_b.end_line,
                head_start_line=h_unit.start_line,
                head_end_line=h_unit.end_line,
                base_text=best_b.original_text,
                head_text=h_unit.original_text,
            )
            unit_diffs.append(diff_item)
            diff_by_head_unit_id[h_unit.unit_id] = diff_item
            diff_by_base_unit_id[best_b.unit_id] = diff_item

    # 4. Remaining unmatched base units -> deleted
    for b_unit in unmatched_base:
        if b_unit.unit_id in matched_base_unit_ids:
            continue
        diff_item = DocumentationUnitDiff(
            documentation_file=b_unit.documentation_file,
            previous_file=None,
            change_type="deleted",
            section_heading=b_unit.section_heading,
            base_unit_id=b_unit.unit_id,
            head_unit_id=None,
            base_start_line=b_unit.start_line,
            base_end_line=b_unit.end_line,
            head_start_line=None,
            head_end_line=None,
            base_text=b_unit.original_text,
            head_text=None,
        )
        unit_diffs.append(diff_item)
        diff_by_base_unit_id[b_unit.unit_id] = diff_item

    # 5. Remaining unmatched head units -> added
    for h_unit in unmatched_head:
        if h_unit.unit_id in matched_head_unit_ids:
            continue
        diff_item = DocumentationUnitDiff(
            documentation_file=h_unit.documentation_file,
            previous_file=None,
            change_type="added",
            section_heading=h_unit.section_heading,
            base_unit_id=None,
            head_unit_id=h_unit.unit_id,
            base_start_line=None,
            base_end_line=None,
            head_start_line=h_unit.start_line,
            head_end_line=h_unit.end_line,
            base_text=None,
            head_text=h_unit.original_text,
        )
        unit_diffs.append(diff_item)
        diff_by_head_unit_id[h_unit.unit_id] = diff_item

    return file_changes, unit_diffs, diff_by_head_unit_id, diff_by_base_unit_id


def _pair_units_in_file(
    base_file: str,
    head_file: str,
    base_units: List[DocumentationUnit],
    head_units: List[DocumentationUnit],
    is_file_renamed: bool,
    matched_base_unit_ids: Set[str],
    matched_head_unit_ids: Set[str],
    unit_diffs: List[DocumentationUnitDiff],
    diff_by_head_unit_id: Dict[str, DocumentationUnitDiff],
    diff_by_base_unit_id: Dict[str, DocumentationUnitDiff],
) -> None:
    """Pair base and head units belonging to the same (or renamed) documentation file."""
    # Pass 1: Exact text + section heading match
    for h_unit in head_units:
        if h_unit.unit_id in matched_head_unit_ids:
            continue
        for b_unit in base_units:
            if b_unit.unit_id in matched_base_unit_ids:
                continue
            if (
                b_unit.section_heading == h_unit.section_heading
                and b_unit.original_text.strip() == h_unit.original_text.strip()
            ):
                matched_base_unit_ids.add(b_unit.unit_id)
                matched_head_unit_ids.add(h_unit.unit_id)
                c_type = "moved" if is_file_renamed else "unchanged"
                diff_item = DocumentationUnitDiff(
                    documentation_file=head_file,
                    previous_file=base_file if is_file_renamed else None,
                    change_type=c_type,
                    section_heading=h_unit.section_heading,
                    base_unit_id=b_unit.unit_id,
                    head_unit_id=h_unit.unit_id,
                    base_start_line=b_unit.start_line,
                    base_end_line=b_unit.end_line,
                    head_start_line=h_unit.start_line,
                    head_end_line=h_unit.end_line,
                    base_text=b_unit.original_text,
                    head_text=h_unit.original_text,
                )
                unit_diffs.append(diff_item)
                diff_by_head_unit_id[h_unit.unit_id] = diff_item
                diff_by_base_unit_id[b_unit.unit_id] = diff_item
                break

    # Pass 2: Modified units in the same section or sharing code identifiers / similarity
    for h_unit in head_units:
        if h_unit.unit_id in matched_head_unit_ids:
            continue
        best_b: Optional[DocumentationUnit] = None
        best_score = 0.0
        for b_unit in base_units:
            if b_unit.unit_id in matched_base_unit_ids:
                continue
            same_section = b_unit.section_heading == h_unit.section_heading
            text_ratio = SequenceMatcher(
                None, b_unit.original_text.strip(), h_unit.original_text.strip()
            ).ratio()
            shared_idents = set(b_unit.referenced_identifiers) & set(
                h_unit.referenced_identifiers
            )

            score = text_ratio
            if same_section:
                score += 0.35
            if b_unit.unit_type == h_unit.unit_type:
                score += 0.15
            if shared_idents:
                score += 0.25

            if score >= 0.45 and score > best_score:
                best_score = score
                best_b = b_unit

        if best_b is not None:
            matched_base_unit_ids.add(best_b.unit_id)
            matched_head_unit_ids.add(h_unit.unit_id)
            c_type = (
                "moved"
                if (
                    is_file_renamed
                    and best_b.original_text.strip() == h_unit.original_text.strip()
                )
                else "modified"
            )
            diff_item = DocumentationUnitDiff(
                documentation_file=head_file,
                previous_file=base_file if is_file_renamed else None,
                change_type=c_type,
                section_heading=h_unit.section_heading or best_b.section_heading,
                base_unit_id=best_b.unit_id,
                head_unit_id=h_unit.unit_id,
                base_start_line=best_b.start_line,
                base_end_line=best_b.end_line,
                head_start_line=h_unit.start_line,
                head_end_line=h_unit.end_line,
                base_text=best_b.original_text,
                head_text=h_unit.original_text,
            )
            unit_diffs.append(diff_item)
            diff_by_head_unit_id[h_unit.unit_id] = diff_item
            diff_by_base_unit_id[best_b.unit_id] = diff_item
