"""
Reproducible Evaluation Dataset & Quality Metrics Calculator for DocGuard (Milestone 7).

Evaluates the actual deterministic DocGuard pipeline (AST extraction, change detection,
Markdown parsing, statement extraction, doc-to-code mapping, historical doc comparison,
and drift detection rules A–I) against a labeled 16-case benchmark dataset and computes:
- True Positives (TP)
- False Positives (FP)
- True Negatives (TN)
- False Negatives (FN)
- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 * Precision * Recall / (Precision + Recall)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.analyzers.change_detector import detect_symbol_changes
from app.analyzers.documentation_comparator import compare_documentation_across_commits
from app.analyzers.documentation_extractor import extract_documentation_units
from app.analyzers.documentation_mapper import map_documentation_units_to_symbols
from app.analyzers.drift_detector import detect_documentation_drift
from app.analyzers.markdown_parser import parse_markdown_document
from app.analyzers.symbol_extractor import extract_python_symbols


@dataclass
class EvaluationCase:
    """A single labeled benchmark case for evaluating drift detection accuracy."""

    case_id: str
    description: str
    base_py: Dict[str, str]
    head_py: Dict[str, str]
    base_md: Dict[str, str]
    head_md: Dict[str, str]
    expected_unresolved_drift: bool
    expected_rule_id: Optional[str] = None
    deleted_py_files: Set[str] = field(default_factory=set)


@dataclass
class CaseEvaluationResult:
    """Measured outcome for a single benchmark case."""

    case_id: str
    description: str
    expected_unresolved_drift: bool
    actual_unresolved_drift: bool
    expected_rule_id: Optional[str]
    actual_rule_ids: List[str]
    outcome_label: str  # "TP" | "FP" | "TN" | "FN"


@dataclass
class BenchmarkEvaluationReport:
    """Aggregated quality metrics across the evaluation benchmark dataset."""

    total_cases: int
    positive_cases: int
    negative_cases: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    case_results: List[CaseEvaluationResult]
    dataset_limitation_note: str


def build_labeled_evaluation_dataset() -> List[EvaluationCase]:
    """
    Return the 16-case controlled benchmark dataset (8 ground-truth positive drift
    cases across Rules A–H and 8 ground-truth negative non-drift / false-positive
    trap cases).
    """
    return [
        # --- 8 Ground-Truth Positive Cases (expected_unresolved_drift = True) ---
        EvaluationCase(
            case_id="case-01-changed-default",
            description="Default parameter changed while docs still state old default literal",
            base_py={"src/users.py": "def create_user(role='user'):\n    return role\n"},
            head_py={"src/users.py": "def create_user(role='admin'):\n    return role\n"},
            base_md={"docs/api.md": "## create_user()\n\nThe default `role` is `user`.\n"},
            head_md={"docs/api.md": "## create_user()\n\nThe default `role` is `user`.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_A_CHANGED_DEFAULT",
        ),
        EvaluationCase(
            case_id="case-02-removed-parameter",
            description="Documented parameter removed from function signature",
            base_py={"src/net.py": "def connect(host, port):\n    return (host, port)\n"},
            head_py={"src/net.py": "def connect(host):\n    return host\n"},
            base_md={"docs/api.md": "## connect()\n\nPass the `port` parameter to `connect(host, port)`.\n"},
            head_md={"docs/api.md": "## connect()\n\nPass the `port` parameter to `connect(host, port)`.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_B_REMOVED_OR_RENAMED_PARAMETER",
        ),
        EvaluationCase(
            case_id="case-03-renamed-parameter",
            description="Documented parameter renamed while docs still use old parameter name",
            base_py={"src/alert.py": "def send_alert(user_addr: str) -> bool:\n    return True\n"},
            head_py={"src/alert.py": "def send_alert(email_addr: str) -> bool:\n    return True\n"},
            base_md={"docs/api.md": "## send_alert()\n\nPass `user_addr` to `send_alert(user_addr)`.\n"},
            head_md={"docs/api.md": "## send_alert()\n\nPass `user_addr` to `send_alert(user_addr)`.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_B_REMOVED_OR_RENAMED_PARAMETER",
        ),
        EvaluationCase(
            case_id="case-04-added-required-parameter",
            description="Required parameter added while docs show call without it",
            base_py={"src/msg.py": "def send_message(message):\n    return message\n"},
            head_py={"src/msg.py": "def send_message(message, recipient):\n    return (message, recipient)\n"},
            base_md={"docs/api.md": "## send_message()\n\nCall `send_message(message)` to send a message.\n"},
            head_md={"docs/api.md": "## send_message()\n\nCall `send_message(message)` to send a message.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_C_ADDED_REQUIRED_PARAMETER",
        ),
        EvaluationCase(
            case_id="case-05-changed-return-annotation",
            description="Return annotation changed while docs describe old return type",
            base_py={"src/tax.py": "def compute_tax(amount: float) -> float:\n    return amount * 0.1\n"},
            head_py={"src/tax.py": "def compute_tax(amount: float) -> dict:\n    return {'tax': amount * 0.1}\n"},
            base_md={"docs/api.md": "## compute_tax()\n\nReturns a `float` tax value.\n"},
            head_md={"docs/api.md": "## compute_tax()\n\nReturns a `float` tax value.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_D_RETURN_CONTRACT_CHANGED",
        ),
        EvaluationCase(
            case_id="case-06-removed-function",
            description="Documented function removed in head commit",
            base_py={"src/core.py": "def legacy_export(data):\n    return data\n"},
            head_py={"src/core.py": "def current_helper():\n    return True\n"},
            base_md={"docs/api.md": "## legacy_export()\n\nCall `legacy_export(data)` to export records.\n"},
            head_md={"docs/api.md": "## legacy_export()\n\nCall `legacy_export(data)` to export records.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_E_SYMBOL_REMOVED",
        ),
        EvaluationCase(
            case_id="case-07-renamed-function",
            description="Documented function confidently renamed while docs still reference old name",
            base_py={
                "src/billing.py": (
                    "def calculate_invoice_subtotal(items, tax_rate=0.05):\n"
                    "    subtotal = sum(i.price * i.qty for i in items)\n"
                    "    return round(subtotal * (1 + tax_rate), 2)\n"
                )
            },
            head_py={
                "src/billing.py": (
                    "def compute_invoice_total(items, tax_rate=0.05):\n"
                    "    subtotal = sum(i.price * i.qty for i in items)\n"
                    "    return round(subtotal * (1 + tax_rate), 2)\n"
                )
            },
            base_md={"docs/api.md": "## calculate_invoice_subtotal()\n\nCall `calculate_invoice_subtotal(items)`.\n"},
            head_md={"docs/api.md": "## calculate_invoice_subtotal()\n\nCall `calculate_invoice_subtotal(items)`.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_F_SYMBOL_RENAMED",
        ),
        EvaluationCase(
            case_id="case-08-deleted-source-file",
            description="Documented Python source file deleted in head commit",
            base_py={"src/deprecated_api.py": "def old_endpoint():\n    return 200\n"},
            head_py={},
            base_md={"docs/api.md": "## Legacy Module\n\nImport `old_endpoint()` from `src/deprecated_api.py`.\n"},
            head_md={"docs/api.md": "## Legacy Module\n\nImport `old_endpoint()` from `src/deprecated_api.py`.\n"},
            expected_unresolved_drift=True,
            expected_rule_id="RULE_G_DELETED_SOURCE_FILE",
            deleted_py_files={"src/deprecated_api.py"},
        ),
        # --- 8 Ground-Truth Negative Cases (expected_unresolved_drift = False) ---
        EvaluationCase(
            case_id="case-09-optional-parameter-added",
            description="Adding an optional parameter with default value must not trigger drift",
            base_py={"src/msg.py": "def send_message(message):\n    return message\n"},
            head_py={"src/msg.py": "def send_message(message, timeout=30):\n    return (message, timeout)\n"},
            base_md={"docs/api.md": "## send_message()\n\nCall `send_message(message)` to send a message.\n"},
            head_md={"docs/api.md": "## send_message()\n\nCall `send_message(message)` to send a message.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-10-body-only-modification",
            description="Function implementation body change without signature change must not trigger drift",
            base_py={"src/calc.py": "def calculate_fee(amount: float) -> float:\n    return amount * 0.02\n"},
            head_py={"src/calc.py": "def calculate_fee(amount: float) -> float:\n    return max(0.5, amount * 0.02)\n"},
            base_md={"docs/api.md": "## calculate_fee()\n\nCall `calculate_fee(amount)` to compute the fee.\n"},
            head_md={"docs/api.md": "## calculate_fee()\n\nCall `calculate_fee(amount)` to compute the fee.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-11-unrelated-function-parameter-removed",
            description="Removing parameter `port` on unrelated function must not flag `connect(host, port)` docs",
            base_py={
                "src/net.py": (
                    "def connect(host, port):\n    return (host, port)\n\n"
                    "def internal_worker(port):\n    return port\n"
                )
            },
            head_py={
                "src/net.py": (
                    "def connect(host, port):\n    return (host, port)\n\n"
                    "def internal_worker():\n    return 8000\n"
                )
            },
            base_md={"docs/api.md": "## connect()\n\nPass `port` to `connect(host, port)`.\n"},
            head_md={"docs/api.md": "## connect()\n\nPass `port` to `connect(host, port)`.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-12-similar-function-name",
            description="Changes to `calculate_total` must not falsely match `calculate_subtotal` docs",
            base_py={"src/calc.py": "def calculate_total(price, tax):\n    return price + tax\n"},
            head_py={"src/calc.py": "def calculate_total(price):\n    return price\n"},
            base_md={"docs/api.md": "## calculate_subtotal()\n\nPass `tax` to `calculate_subtotal(price, tax)`.\n"},
            head_md={"docs/api.md": "## calculate_subtotal()\n\nPass `tax` to `calculate_subtotal(price, tax)`.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-13-changelog-history-entry",
            description="Historical CHANGELOG.md entries must not be flagged as API drift",
            base_py={"src/calc.py": "def calculate_total(price, tax):\n    return price + tax\n"},
            head_py={"src/calc.py": "def calculate_total(price):\n    return price\n"},
            base_md={"CHANGELOG.md": "# Changelog\n\n- Added `tax` parameter to `calculate_total(price, tax)`.\n"},
            head_md={"CHANGELOG.md": "# Changelog\n\n- Added `tax` parameter to `calculate_total(price, tax)`.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-14-updated-resolved-documentation",
            description="Documentation updated in head commit to match new default is RESOLVED (not unresolved drift)",
            base_py={"src/users.py": "def create_user(role='user'):\n    return role\n"},
            head_py={"src/users.py": "def create_user(role='admin'):\n    return role\n"},
            base_md={"docs/api.md": "## create_user()\n\nThe default `role` is `user`.\n"},
            head_md={"docs/api.md": "## create_user()\n\nThe default `role` is `admin`.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-15-general-overview-prose",
            description="General project overview and installation instructions must not be flagged",
            base_py={"src/users.py": "def create_user(role='user'):\n    return role\n"},
            head_py={"src/users.py": "def create_user(role='admin'):\n    return role\n"},
            base_md={"README.md": "# Overview\n\nWelcome to the platform.\n\n## Installation\n\nRun `pip install app`.\n"},
            head_md={"README.md": "# Overview\n\nWelcome to the platform.\n\n## Installation\n\nRun `pip install app`.\n"},
            expected_unresolved_drift=False,
        ),
        EvaluationCase(
            case_id="case-16-unchanged-code-comments-only",
            description="Comments and whitespace changes in Python code produce zero findings",
            base_py={"src/users.py": "def create_user(role='user'):\n    # comment v1\n    return role\n"},
            head_py={"src/users.py": "def create_user(role='user'):\n    # comment v2\n\n    return role\n"},
            base_md={"docs/api.md": "## create_user()\n\nThe default `role` is `user`.\n"},
            head_md={"docs/api.md": "## create_user()\n\nThe default `role` is `user`.\n"},
            expected_unresolved_drift=False,
        ),
    ]


def _evaluate_single_case(case: EvaluationCase) -> CaseEvaluationResult:
    """Run the real DocGuard drift pipeline on a single EvaluationCase."""
    base_symbols = []
    head_symbols = []
    symbol_changes = []

    all_py_paths = sorted(set(case.base_py.keys()) | set(case.head_py.keys()))
    for py_path in all_py_paths:
        b_src = case.base_py.get(py_path)
        h_src = case.head_py.get(py_path)
        b_syms, _ = (
            extract_python_symbols(b_src, py_path, version="base")
            if b_src is not None
            else ([], None)
        )
        h_syms, _ = (
            extract_python_symbols(h_src, py_path, version="head")
            if h_src is not None
            else ([], None)
        )
        base_symbols.extend(b_syms)
        head_symbols.extend(h_syms)
        if b_src != h_src:
            symbol_changes.extend(detect_symbol_changes(py_path, b_syms, h_syms))

    base_units_by_file = {
        p: extract_documentation_units(parse_markdown_document(txt, p))
        for p, txt in case.base_md.items()
    }
    head_units_by_file = {
        p: extract_documentation_units(parse_markdown_document(txt, p))
        for p, txt in case.head_md.items()
    }

    all_base_units = [u for units in base_units_by_file.values() for u in units]
    all_head_units = [u for units in head_units_by_file.values() for u in units]

    base_mappings = map_documentation_units_to_symbols(all_base_units, base_symbols)
    head_mappings = map_documentation_units_to_symbols(all_head_units, head_symbols)

    (
        _doc_changes,
        _unit_diffs,
        diff_by_head_unit_id,
        diff_by_base_unit_id,
    ) = compare_documentation_across_commits(
        base_units_by_file=base_units_by_file,
        head_units_by_file=head_units_by_file,
        base_raw_by_file=case.base_md,
        head_raw_by_file=case.head_md,
    )

    findings = detect_documentation_drift(
        symbol_changes=symbol_changes,
        deleted_python_files=case.deleted_py_files,
        base_symbols=base_symbols,
        head_symbols=head_symbols,
        base_units=all_base_units,
        head_units=all_head_units,
        base_mappings=base_mappings,
        head_mappings=head_mappings,
        diff_by_head_unit_id=diff_by_head_unit_id,
        diff_by_base_unit_id=diff_by_base_unit_id,
        base_python_sources=case.base_py,
        head_python_sources=case.head_py,
    )

    unresolved_findings = [
        f for f in findings if f.status in {"CONFIRMED_DRIFT", "POTENTIAL_DRIFT"}
    ]
    actual_unresolved = len(unresolved_findings) > 0
    actual_rules = [f.rule_id for f in unresolved_findings]

    if case.expected_unresolved_drift and actual_unresolved:
        outcome = "TP"
    elif not case.expected_unresolved_drift and actual_unresolved:
        outcome = "FP"
    elif not case.expected_unresolved_drift and not actual_unresolved:
        outcome = "TN"
    else:
        outcome = "FN"

    return CaseEvaluationResult(
        case_id=case.case_id,
        description=case.description,
        expected_unresolved_drift=case.expected_unresolved_drift,
        actual_unresolved_drift=actual_unresolved,
        expected_rule_id=case.expected_rule_id,
        actual_rule_ids=actual_rules,
        outcome_label=outcome,
    )


def run_drift_evaluation_benchmark() -> BenchmarkEvaluationReport:
    """
    Execute the full 16-case benchmark dataset and compute TP, FP, TN, FN,
    Precision, Recall, and F1 score with safe zero-denominator handling.
    """
    dataset = build_labeled_evaluation_dataset()
    results = [_evaluate_single_case(c) for c in dataset]

    tp = sum(1 for r in results if r.outcome_label == "TP")
    fp = sum(1 for r in results if r.outcome_label == "FP")
    tn = sum(1 for r in results if r.outcome_label == "TN")
    fn = sum(1 for r in results if r.outcome_label == "FN")

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = (
        round((2 * precision * recall) / (precision + recall), 4)
        if (precision + recall) > 0
        else 0.0
    )

    pos_count = sum(1 for c in dataset if c.expected_unresolved_drift)
    neg_count = sum(1 for c in dataset if not c.expected_unresolved_drift)

    return BenchmarkEvaluationReport(
        total_cases=len(dataset),
        positive_cases=pos_count,
        negative_cases=neg_count,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        case_results=results,
        dataset_limitation_note=(
            "Measured on a controlled 16-case deterministic benchmark dataset (8 positive drift cases, "
            "8 negative false-positive trap cases). While this verifies deterministic rule precision and "
            "recall across supported AST/Markdown patterns, larger real-world corpora with implicit "
            "semantic prose claims will naturally exhibit lower recall."
        ),
    )
