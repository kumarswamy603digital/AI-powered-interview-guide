"""
Static integrity audit of the backend wiring.

FastAPI/SQLAlchemy/pydantic cannot be installed in this sandbox, so the server
cannot be booted. This audit targets the failure classes that a boot would catch:

  1. imports that do not resolve to a real definition
  2. dataclass -> pydantic schema conversions missing required fields
  3. CRUD/model keyword arguments that are not real columns
  4. duplicate or shadowed route paths
  5. SQLAlchemy relationship back_populates that do not pair up
  6. response_model names that do not exist

Dataclasses are introspected at runtime (the engines are dependency-free);
everything else is parsed with ast.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

FAILURES: List[str] = []
WARNINGS: List[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(label)


def warn(message: str) -> None:
    WARNINGS.append(message)


# --------------------------------------------------------------------------
# Parse every module once
# --------------------------------------------------------------------------
FILES: Dict[str, ast.Module] = {}
for path in sorted(BACKEND.rglob("*.py")):
    if "__pycache__" in str(path) or ".ruff_cache" in str(path):
        continue
    rel = path.relative_to(BACKEND)
    module = ".".join(rel.with_suffix("").parts)
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    try:
        FILES[module] = ast.parse(path.read_text())
    except SyntaxError as exc:  # pragma: no cover
        FAILURES.append(f"syntax error in {rel}: {exc}")

print(f"Parsed {len(FILES)} modules\n")


def top_level_names(tree: ast.Module) -> Set[str]:
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Try):
            # Optional-dependency blocks (google.generativeai, pypdf, ...)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        names.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Name):
                            names.add(target.id)
    return names


EXPORTS: Dict[str, Set[str]] = {module: top_level_names(tree) for module, tree in FILES.items()}


# --------------------------------------------------------------------------
# 1. Internal imports resolve
# --------------------------------------------------------------------------
print("=" * 74)
print("1. INTERNAL IMPORT RESOLUTION")
print("=" * 74)

unresolved: List[str] = []
import_count = 0
for module, tree in FILES.items():
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("app"):
            continue
        import_count += 1
        target = node.module
        if target not in EXPORTS:
            unresolved.append(f"{module}: module '{target}' not found")
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            # `from app import models` imports a submodule, not a top-level name.
            if f"{target}.{alias.name}" in EXPORTS:
                continue
            if alias.name not in EXPORTS[target]:
                unresolved.append(f"{module}: '{alias.name}' not defined in {target}")

check(
    f"all {import_count} internal imports resolve",
    not unresolved,
    "\n          ".join(unresolved[:12]),
)


# --------------------------------------------------------------------------
# 2. Dataclass -> pydantic schema compatibility
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("2. DATACLASS -> SCHEMA CONVERSION (model_validate(asdict(...)))")
print("=" * 74)


def schema_fields(module: str, class_name: str) -> Tuple[Set[str], Set[str]]:
    """(all_fields, required_fields) for a pydantic schema, following inheritance."""
    tree = FILES.get(module)
    if tree is None:
        return set(), set()

    target = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            target = node
            break
    if target is None:
        return set(), set()

    all_fields: Set[str] = set()
    required: Set[str] = set()

    # Inherited fields first.
    for base in target.bases:
        if isinstance(base, ast.Name) and base.id not in {"BaseModel"}:
            parent_all, parent_required = schema_fields(module, base.id)
            all_fields |= parent_all
            required |= parent_required

    for node in target.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        if name.startswith("_") or name == "model_config":
            continue
        all_fields.add(name)

        has_default = node.value is not None
        if has_default and isinstance(node.value, ast.Call):
            func = node.value.func
            fname = getattr(func, "id", None) or getattr(func, "attr", None)
            if fname == "Field":
                # Field(...) means required; Field(default=...) / default_factory does not.
                positional_ellipsis = any(
                    isinstance(a, ast.Constant) and a.value is Ellipsis for a in node.value.args
                )
                kwargs = {k.arg for k in node.value.keywords}
                if positional_ellipsis or not ({"default", "default_factory"} & kwargs):
                    has_default = False
        # Optional[...] annotations without a default are still required in pydantic v2.
        if not has_default:
            required.add(name)

    return all_fields, required


# (dataclass import path, dataclass name, schema module, schema name)
PAIRS = [
    ("app.core.attrition", "AttritionAssessment", "app.schemas.workforce", "AttritionAssessmentRead"),
    ("app.core.attrition", "RiskFactor", "app.schemas.workforce", "RiskFactorRead"),
    ("app.core.attrition", "RetentionAction", "app.schemas.workforce", "RetentionActionRead"),
    ("app.core.performance_intel", "PerformanceInsight", "app.schemas.workforce", "PerformanceInsightRead"),
    ("app.core.performance_intel", "ThemeInsight", "app.schemas.workforce", "ThemeInsightRead"),
    ("app.core.performance_intel", "GoalSummary", "app.schemas.workforce", "GoalSummaryRead"),
    ("app.core.performance_intel", "PerformanceAction", "app.schemas.workforce", "PerformanceActionRead"),
    ("app.core.skill_graph", "SkillNode", "app.schemas.workforce", "SkillNodeRead"),
    ("app.core.skill_graph", "ReskillCandidate", "app.schemas.workforce", "ReskillCandidateRead"),
    ("app.core.ranking", "CandidateRanking", "app.schemas.hr", "CandidateRankingRead"),
    ("app.core.ranking", "ScoreComponent", "app.schemas.hr", "ScoreComponentRead"),
    ("app.core.policy_qa", "PolicyAnswer", "app.schemas.policy", "PolicyAnswerRead"),
    ("app.core.policy_qa", "Citation", "app.schemas.policy", "CitationRead"),
    ("app.core.decision_dashboard", "CrossSourceInsight", "app.schemas.workforce", "CrossSourceInsightRead"),
]

# decision_dashboard imports sqlalchemy; stub it so the dataclasses can be read.
import types  # noqa: E402


def _passthrough(*_a, **_k):
    return None


import importlib  # noqa: E402


def _missing(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return False
    except ImportError:
        return True


# Stub only what is absent, so a fully installed environment audits the real code.
if _missing("sqlalchemy"):
    _sa = types.ModuleType("sqlalchemy")
    for _n in ("JSON", "Column", "Date", "DateTime", "Float", "ForeignKey", "Integer",
               "String", "Text", "Boolean", "create_engine", "func", "UniqueConstraint"):
        setattr(_sa, _n, _passthrough)
    _sa_orm = types.ModuleType("sqlalchemy.orm")
    _sa_orm.relationship = _passthrough
    _sa_orm.sessionmaker = _passthrough
    _sa_orm.declarative_base = lambda: type("Base", (), {})
    _sa_orm.Session = object
    _sa.orm = _sa_orm
    _sa_exc = types.ModuleType("sqlalchemy.exc")
    _sa_exc.IntegrityError = type("IntegrityError", (Exception,), {})
    sys.modules["sqlalchemy"] = _sa
    sys.modules["sqlalchemy.orm"] = _sa_orm
    sys.modules["sqlalchemy.exc"] = _sa_exc
if _missing("pydantic"):
    _pyd = types.ModuleType("pydantic")
    _pyd.AnyHttpUrl = str
    _pyd.BaseModel = object
    sys.modules["pydantic"] = _pyd
if _missing("pydantic_settings"):
    _pyds = types.ModuleType("pydantic_settings")
    _pyds.BaseSettings = object
    sys.modules["pydantic_settings"] = _pyds

problems: List[str] = []
for dc_module, dc_name, schema_module, schema_name in PAIRS:
    try:
        mod = importlib.import_module(dc_module)
        dc = getattr(mod, dc_name)
        dc_field_names = {f.name for f in dataclasses.fields(dc)}
    except Exception as exc:
        problems.append(f"{dc_module}.{dc_name}: could not introspect ({exc})")
        continue

    all_fields, required = schema_fields(schema_module, schema_name)
    if not all_fields:
        problems.append(f"{schema_module}.{schema_name}: schema not found or has no fields")
        continue

    missing_required = required - dc_field_names
    if missing_required:
        problems.append(
            f"{schema_name} requires {sorted(missing_required)} which {dc_name} does not provide"
        )
    dropped = dc_field_names - all_fields
    if dropped:
        warn(f"{dc_name} -> {schema_name}: dataclass fields not exposed by the schema: {sorted(dropped)}")

check(
    f"all {len(PAIRS)} dataclass->schema conversions supply every required field",
    not problems,
    "\n          ".join(problems[:10]),
)


# --------------------------------------------------------------------------
# 3. CRUD / model keyword arguments are real columns
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("3. MODEL KEYWORD ARGUMENTS")
print("=" * 74)

MODEL_MODULES = [m for m in FILES if m.startswith("app.models")]
MODEL_COLUMNS: Dict[str, Set[str]] = {}
MODEL_RELATIONSHIPS: Dict[str, Dict[str, dict]] = {}

for module in MODEL_MODULES:
    for node in FILES[module].body:
        if not isinstance(node, ast.ClassDef):
            continue
        columns: Set[str] = set()
        relationships: Dict[str, dict] = {}
        for item in node.body:
            if not isinstance(item, ast.Assign) or not isinstance(item.targets[0], ast.Name):
                continue
            name = item.targets[0].id
            value = item.value
            if not isinstance(value, ast.Call):
                continue
            func_name = getattr(value.func, "id", None) or getattr(value.func, "attr", None)
            if func_name == "Column":
                columns.add(name)
            elif func_name == "relationship":
                target_model = None
                if value.args and isinstance(value.args[0], ast.Constant):
                    target_model = value.args[0].value
                kwargs = {
                    k.arg: (k.value.value if isinstance(k.value, ast.Constant) else "<expr>")
                    for k in value.keywords
                }
                relationships[name] = {"target": target_model, **kwargs}
        if columns or relationships:
            MODEL_COLUMNS[node.name] = columns
            MODEL_RELATIONSHIPS[node.name] = relationships

print(f"  models discovered: {', '.join(sorted(MODEL_COLUMNS))}\n")

# crud function -> model it instantiates
CRUD_MODEL = {
    "create_employee": "Employee",
    "create_review": "PerformanceReview",
    "create_goal": "Goal",
    "create_feedback": "Feedback",
    "create_skill_requirement": "SkillRequirement",
    "record_attendance": "AttendanceRecord",
    "create_policy": "PolicyDocument",
    "create_onboarding_plan": "OnboardingPlan",
}
# Extra kwargs these helpers accept beyond columns.
EXTRA_OK = {"create_policy": {"chunks"}, "create_onboarding_plan": {"tasks"}}

bad_kwargs: List[str] = []
call_count = 0
for module, tree in FILES.items():
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fname not in CRUD_MODEL:
            continue
        model = CRUD_MODEL[fname]
        allowed = MODEL_COLUMNS.get(model, set()) | EXTRA_OK.get(fname, set())
        if not allowed:
            continue
        call_count += 1
        for keyword in node.keywords:
            if keyword.arg is None:
                continue  # **kwargs splat
            if keyword.arg not in allowed:
                bad_kwargs.append(
                    f"{module}: {fname}(..., {keyword.arg}=...) is not a column of {model}"
                )

check(
    f"all {call_count} CRUD create calls use real columns",
    not bad_kwargs,
    "\n          ".join(bad_kwargs[:12]),
)

# Direct model construction (seed script writes some rows directly).
direct_bad: List[str] = []
direct_count = 0
for module, tree in FILES.items():
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None)
        if fname not in MODEL_COLUMNS:
            continue
        allowed = MODEL_COLUMNS[fname] | set(MODEL_RELATIONSHIPS.get(fname, {}))
        direct_count += 1
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg not in allowed:
                direct_bad.append(f"{module}: {fname}({keyword.arg}=...) is not a column")

check(
    f"all {direct_count} direct model constructions use real columns",
    not direct_bad,
    "\n          ".join(direct_bad[:12]),
)


# --------------------------------------------------------------------------
# 4. Relationship back_populates pair up
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("4. SQLALCHEMY RELATIONSHIP INTEGRITY")
print("=" * 74)

rel_problems: List[str] = []
rel_count = 0
for model, relationships in MODEL_RELATIONSHIPS.items():
    for attr, spec in relationships.items():
        target = spec.get("target")
        if not target:
            continue
        rel_count += 1
        if target not in MODEL_COLUMNS:
            rel_problems.append(f"{model}.{attr} -> unknown model '{target}'")
            continue
        back = spec.get("back_populates")
        if back and back != "<expr>":
            target_rels = MODEL_RELATIONSHIPS.get(target, {})
            if back not in target_rels:
                rel_problems.append(
                    f"{model}.{attr}.back_populates='{back}' but {target} has no '{back}' relationship"
                )
            else:
                mirror = target_rels[back].get("back_populates")
                if mirror and mirror != attr:
                    rel_problems.append(
                        f"{model}.{attr} <-> {target}.{back} disagree "
                        f"(mirror points at '{mirror}')"
                    )

check(
    f"all {rel_count} relationships reference known models and pair correctly",
    not rel_problems,
    "\n          ".join(rel_problems[:12]),
)

# Every model with a ForeignKey to another table should be reachable in models/__init__
init_exports = EXPORTS.get("app.models", set())
missing_from_init = [m for m in MODEL_COLUMNS if m not in init_exports]
check(
    "every model is imported in app/models/__init__.py (so create_all sees it)",
    not missing_from_init,
    f"missing: {missing_from_init}",
)


# --------------------------------------------------------------------------
# 5. Routes: prefixes, duplicates, response models
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("5. ROUTE TABLE")
print("=" * 74)

ROUTES: List[Tuple[str, str, str, str]] = []  # (method, full_path, module, response_model)
route_problems: List[str] = []

for module, tree in FILES.items():
    if ".routes." not in module:
        continue
    prefix = ""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "router" and isinstance(node.value, ast.Call):
                for keyword in node.value.keywords:
                    if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                        prefix = keyword.value.value

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "router"):
                continue
            method = func.attr.upper()
            path = ""
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = decorator.args[0].value
            response_model = None
            for keyword in decorator.keywords:
                if keyword.arg == "response_model":
                    response_model = ast.unparse(keyword.value)
            ROUTES.append((method, prefix + path, module, response_model or ""))

print(f"  {len(ROUTES)} routes registered")

# Duplicate (method, path)
seen: Dict[Tuple[str, str], str] = {}
for method, path, module, _rm in ROUTES:
    key = (method, path)
    if key in seen:
        route_problems.append(f"duplicate route {method} {path} in {module} and {seen[key]}")
    seen[key] = module

check("no duplicate (method, path) pairs", not route_problems, "\n          ".join(route_problems))

# Static segments must not be shadowed by a path parameter on the same prefix.
shadow_problems: List[str] = []
for method, path, module, _rm in ROUTES:
    parts = path.strip("/").split("/")
    for other_method, other_path, other_module, _orm in ROUTES:
        if (method, path) == (other_method, other_path) or method != other_method:
            continue
        other_parts = other_path.strip("/").split("/")
        if len(parts) != len(other_parts):
            continue
        # Does `other` have a {param} where `path` has a static segment, earlier in file order?
        pairs = list(zip(parts, other_parts))
        if all(
            a == b or (b.startswith("{") and not a.startswith("{"))
            for a, b in pairs
        ) and any(b.startswith("{") and not a.startswith("{") for a, b in pairs):
            # `other` is the generic one; it must be declared AFTER the specific one.
            if ROUTES.index((other_method, other_path, other_module, _orm)) < ROUTES.index(
                (method, path, module, _rm)
            ) and other_module == module:
                shadow_problems.append(
                    f"{other_method} {other_path} ({other_module}) is declared before "
                    f"{method} {path} and will shadow it"
                )

check(
    "no path-parameter route shadows a more specific static route",
    not shadow_problems,
    "\n          ".join(sorted(set(shadow_problems))[:10]),
)

# response_model symbols must be imported in their module
rm_problems: List[str] = []
for method, path, module, response_model in ROUTES:
    if not response_model or response_model in {"dict", "None"}:
        continue
    root = (
        response_model.replace("List[", "")
        .replace("list[", "")
        .replace("Optional[", "")
        .replace("]", "")
        .strip()
    )
    if root in {"dict", "str", "int", "float", "bool"}:
        continue
    if root not in EXPORTS.get(module, set()):
        rm_problems.append(f"{module}: response_model '{root}' for {method} {path} not imported")

check("every response_model symbol is imported in its route module", not rm_problems,
      "\n          ".join(rm_problems[:10]))

# All routers are registered in main.py
main_tree = FILES.get("app.main")
registered: Set[str] = set()
if main_tree:
    for node in ast.walk(main_tree):
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None)
            if fname == "include_router" and node.args:
                registered.add(ast.unparse(node.args[0]))
route_modules = {m for _me, _p, m, _rm in ROUTES}
imported_routers = {
    f"{alias.asname}"
    for node in ast.walk(main_tree or ast.Module(body=[], type_ignores=[]))
    if isinstance(node, ast.ImportFrom) and node.module and ".routes." in node.module
    for alias in node.names
    if alias.asname
}
unregistered = imported_routers - registered
check(
    f"all {len(imported_routers)} imported routers are included in the app",
    not unregistered,
    f"not registered: {sorted(unregistered)}",
)
missing_router_import = {
    m.split(".")[-1] for m in route_modules
} - {r.replace("_router", "") for r in imported_routers}
check(
    "every route module is wired into main.py",
    not missing_router_import,
    f"route modules not imported: {sorted(missing_router_import)}",
)


# --------------------------------------------------------------------------
# 6. Engine <-> service layer signature agreement
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("6. SERVICE LAYER CALLS INTO ENGINES")
print("=" * 74)

sig_problems: List[str] = []
ENGINE_DATACLASSES = {
    "EmployeeSignals": "app.core.attrition",
    "PerformanceSignals": "app.core.performance_intel",
    "ReviewInput": "app.core.performance_intel",
    "GoalInput": "app.core.performance_intel",
    "FeedbackInput": "app.core.performance_intel",
    "EmployeeSkillProfile": "app.core.skill_graph",
    "SkillHolding": "app.core.skill_graph",
    "RequirementInput": "app.core.skill_graph",
    "OnboardingProfile": "app.core.onboarding_agent",
    "PolicyChunkInput": "app.core.policy_qa",
    "EmployeeContext": "app.core.policy_qa",
    "CandidateEvidence": "app.core.ranking",
    "JobRequirements": "app.core.ranking",
}

for module, tree in FILES.items():
    if not module.startswith("app."):
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None)
        if fname not in ENGINE_DATACLASSES:
            continue
        try:
            dc = getattr(importlib.import_module(ENGINE_DATACLASSES[fname]), fname)
            valid = {f.name for f in dataclasses.fields(dc)}
        except Exception:
            continue
        for keyword in node.keywords:
            if keyword.arg and keyword.arg not in valid:
                sig_problems.append(
                    f"{module}: {fname}({keyword.arg}=...) is not a field of {fname}"
                )

check(
    "every engine dataclass construction uses real fields",
    not sig_problems,
    "\n          ".join(sig_problems[:12]),
)


# --------------------------------------------------------------------------
# 7. Seed script references
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("7. SEED SCRIPT INTEGRITY")
print("=" * 74)

seed = FILES.get("scripts.seed_demo")
check("seed script parses", seed is not None)

if seed:
    # Every model it deletes in reset must be imported.
    seed_names = EXPORTS["scripts.seed_demo"]
    owned: List[str] = []
    for node in ast.walk(seed):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "OWNED_TABLES" and isinstance(node.value, ast.List):
                owned = [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    check(
        f"all {len(owned)} tables in OWNED_TABLES are imported",
        all(name in seed_names for name in owned),
        f"missing: {[n for n in owned if n not in seed_names]}",
    )
    check(
        "OWNED_TABLES deletes children before parents",
        owned.index("OnboardingTask") < owned.index("OnboardingPlan")
        and owned.index("PolicyChunk") < owned.index("PolicyDocument")
        and owned.index("InterviewTurn") < owned.index("InterviewSession")
        and owned.index("EmployeeSkill") < owned.index("Employee")
        and owned.index("Resume") < owned.index("Candidate")
        and owned.index("Candidate") < owned.index("JobRequisition"),
        f"order: {owned}",
    )
    check(
        "seed covers every owned model that routes expose",
        {"Employee", "PerformanceReview", "Goal", "Feedback", "AttendanceRecord",
         "SkillRequirement", "PolicyDocument", "OnboardingPlan", "Candidate",
         "JobRequisition", "InterviewSession"} <= set(owned),
        f"owned: {sorted(owned)}",
    )


# --------------------------------------------------------------------------
# 8. Schema <-> ORM compatibility (model_validate on an ORM row)
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("8. SCHEMA <-> ORM COMPATIBILITY")
print("=" * 74)


def schema_annotations(module: str, class_name: str) -> Dict[str, str]:
    """field -> unparsed annotation, following base classes."""
    tree = FILES.get(module)
    if tree is None:
        return {}
    target = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None
    )
    if target is None:
        return {}

    annotations: Dict[str, str] = {}
    for base in target.bases:
        if isinstance(base, ast.Name) and base.id != "BaseModel":
            annotations.update(schema_annotations(module, base.id))
    for node in target.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotations[node.target.id] = ast.unparse(node.annotation)
    return annotations


def before_validated_fields(module: str, class_name: str) -> Set[str]:
    """Fields covered by a mode='before' validator, following base classes."""
    tree = FILES.get(module)
    if tree is None:
        return set()
    target = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None
    )
    if target is None:
        return set()

    covered: Set[str] = set()
    for base in target.bases:
        if isinstance(base, ast.Name) and base.id != "BaseModel":
            covered |= before_validated_fields(module, base.id)

    for node in target.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            name = getattr(decorator.func, "id", None) or getattr(decorator.func, "attr", None)
            if name != "field_validator":
                continue
            if not any(
                k.arg == "mode" and isinstance(k.value, ast.Constant) and k.value.value == "before"
                for k in decorator.keywords
            ):
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    covered.add(arg.value)
    return covered


# Nullable JSON / relationship info per model.
MODEL_NULLABLE_JSON: Dict[str, Set[str]] = {}
MODEL_NULLABLE_COLUMNS: Dict[str, Set[str]] = {}
for module in MODEL_MODULES:
    for node in FILES[module].body:
        if not isinstance(node, ast.ClassDef):
            continue
        nullable_json: Set[str] = set()
        nullable_any: Set[str] = set()
        for item in node.body:
            if not isinstance(item, ast.Assign) or not isinstance(item.targets[0], ast.Name):
                continue
            value = item.value
            if not isinstance(value, ast.Call):
                continue
            if (getattr(value.func, "id", None) or getattr(value.func, "attr", None)) != "Column":
                continue
            name = item.targets[0].id
            is_json = any(getattr(a, "id", None) == "JSON" for a in value.args)
            nullable = True  # SQLAlchemy default
            for keyword in value.keywords:
                if keyword.arg == "nullable" and isinstance(keyword.value, ast.Constant):
                    nullable = bool(keyword.value.value)
                if keyword.arg == "primary_key" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value:
                        nullable = False
            if nullable:
                nullable_any.add(name)
                if is_json:
                    nullable_json.add(name)
        MODEL_NULLABLE_JSON[node.name] = nullable_json
        MODEL_NULLABLE_COLUMNS[node.name] = nullable_any

# (schema module, schema class, ORM model) - schemas built via model_validate(orm_row)
SCHEMA_ORM_PAIRS = [
    ("app.schemas.workforce", "EmployeeRead", "Employee"),
    ("app.schemas.workforce", "EmployeeSkillRead", "EmployeeSkill"),
    ("app.schemas.workforce", "AttendanceRead", "AttendanceRecord"),
    ("app.schemas.workforce", "ReviewRead", "PerformanceReview"),
    ("app.schemas.workforce", "GoalRead", "Goal"),
    ("app.schemas.workforce", "FeedbackRead", "Feedback"),
    ("app.schemas.workforce", "SkillRequirementRead", "SkillRequirement"),
    ("app.schemas.hr", "JobRequisitionRead", "JobRequisition"),
    ("app.schemas.hr", "CandidateRead", "Candidate"),
    ("app.schemas.resume", "ResumeRead", "Resume"),
    ("app.schemas.policy", "PolicyRead", "PolicyDocument"),
    ("app.schemas.policy", "PolicyChunkRead", "PolicyChunk"),
    ("app.schemas.onboarding", "OnboardingTaskRead", "OnboardingTask"),
]

collisions: List[str] = []
null_json: List[str] = []
null_scalar: List[str] = []

for schema_module, schema_name, model_name in SCHEMA_ORM_PAIRS:
    annotations = schema_annotations(schema_module, schema_name)
    if not annotations:
        collisions.append(f"{schema_module}.{schema_name}: schema not found")
        continue
    _all, required = schema_fields(schema_module, schema_name)
    covered = before_validated_fields(schema_module, schema_name)
    relationships = set(MODEL_RELATIONSHIPS.get(model_name, {}))
    nullable_json = MODEL_NULLABLE_JSON.get(model_name, set())
    nullable_columns = MODEL_NULLABLE_COLUMNS.get(model_name, set())

    for field_name, annotation in annotations.items():
        if field_name in {"model_config"} or field_name.startswith("_"):
            continue
        is_list = annotation.startswith("List[") or annotation.startswith("list[")
        is_optional = annotation.startswith("Optional[") or "None" in annotation

        # (a) schema field name collides with an ORM relationship -> the raw value
        #     is a list of model instances, not the declared type.
        if field_name in relationships and field_name not in covered:
            collisions.append(
                f"{schema_name}.{field_name} shadows the {model_name}.{field_name} "
                f"relationship and has no mode='before' validator"
            )

        # (b) nullable JSON column read into a non-Optional list -> None fails.
        if is_list and field_name in nullable_json and field_name not in covered:
            null_json.append(
                f"{schema_name}.{field_name} reads nullable JSON column "
                f"{model_name}.{field_name}; NULL will fail List validation"
            )

        # (c) required non-Optional scalar backed by a nullable column.
        if (
            field_name in required
            and not is_optional
            and not is_list
            and field_name in nullable_columns
            and field_name not in covered
        ):
            null_scalar.append(
                f"{schema_name}.{field_name} is required but {model_name}.{field_name} is nullable"
            )

check(
    f"no schema field shadows an ORM relationship unguarded ({len(SCHEMA_ORM_PAIRS)} schemas)",
    not collisions,
    "\n          ".join(collisions[:10]),
)
check(
    "no nullable JSON column feeds an unguarded list field",
    not null_json,
    "\n          ".join(null_json[:10]),
)
check(
    "no required scalar field is backed by a nullable column",
    not null_scalar,
    "\n          ".join(null_scalar[:10]),
)


# --------------------------------------------------------------------------
# 9. The HTTP smoke test only calls paths that exist
# --------------------------------------------------------------------------
print()
print("=" * 74)
print("9. HTTP SMOKE TEST COVERAGE")
print("=" * 74)


def _normalise_path(path: str) -> str:
    """Strip the query string and reduce every path parameter to a placeholder."""
    path = path.split("?", 1)[0]
    return re.sub(r"\{[^}]*\}", "{}", path)


def _path_matches(called: str, route: str) -> bool:
    """
    Does a called path match a route pattern?

    Segment-wise, where a route parameter matches anything and a call-site
    placeholder (from an f-string) or a literal value (e.g. '999999',
    'Kubernetes') both satisfy it.
    """
    called_parts = called.strip("/").split("/")
    route_parts = route.strip("/").split("/")
    if len(called_parts) != len(route_parts):
        return False
    return all(
        route_part == "{}" or called_part == "{}" or route_part == called_part
        for route_part, called_part in zip(route_parts, called_parts)
    )


smoke = FILES.get("scripts.smoke_http")
check("smoke test script parses", smoke is not None)

if smoke:
    route_keys = {(m, _normalise_path(p)) for m, p, _mod, _rm in ROUTES}
    route_keys.add(("GET", "/health"))

    called: Set[Tuple[str, str]] = set()
    for node in ast.walk(smoke):
        if not isinstance(node, ast.Call):
            continue
        func_name = getattr(node.func, "id", None)
        if func_name not in {"request", "expect_ok"}:
            continue
        # request(method, path, ...) / expect_ok(label, method, path, ...)
        offset = 0 if func_name == "request" else 1
        if len(node.args) < offset + 2:
            continue
        method_node, path_node = node.args[offset], node.args[offset + 1]
        if not (isinstance(method_node, ast.Constant) and isinstance(method_node.value, str)):
            continue
        method = method_node.value.upper()

        if isinstance(path_node, ast.Constant) and isinstance(path_node.value, str):
            path = path_node.value
        elif isinstance(path_node, ast.JoinedStr):
            parts: List[str] = []
            for value in path_node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                else:
                    parts.append("{}")
            path = "".join(parts)
        else:
            continue
        called.add((method, _normalise_path(path)))

    unknown = sorted(
        f"{method} {path}"
        for method, path in called
        if not any(
            route_method == method and _path_matches(path, route_path)
            for route_method, route_path in route_keys
        )
    )
    check(
        f"all {len(called)} paths called by the smoke test exist in the route table",
        not unknown,
        "\n          ".join(unknown[:12]),
    )

    # Which capability endpoints does the smoke test leave untouched?
    capability_prefixes = [
        "/api/employees", "/api/attrition", "/api/performance", "/api/skills",
        "/api/onboarding", "/api/policies", "/api/candidates", "/api/jobs",
        "/api/hr", "/api/interviews", "/api/resumes", "/api/attendance",
    ]
    relevant = {
        (m, _normalise_path(p))
        for m, p, _mod, _rm in ROUTES
        if any(p.startswith(prefix) for prefix in capability_prefixes)
    }
    uncovered = sorted(
        f"{route_method} {route_path}"
        for route_method, route_path in relevant
        if not any(
            called_method == route_method and _path_matches(called_path, route_path)
            for called_method, called_path in called
        )
    )
    coverage = (len(relevant) - len(uncovered)) / len(relevant) * 100 if relevant else 0.0
    print(f"  note: smoke test covers {coverage:.0f}% of capability endpoints "
          f"({len(relevant) - len(uncovered)}/{len(relevant)})")
    for path in uncovered:
        warn(f"not exercised by the smoke test: {path}")
    check("smoke test covers at least 70% of capability endpoints", coverage >= 70.0,
          f"{coverage:.0f}%")


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
print()
print("=" * 74)
print(f"AUDIT SUMMARY — {CHECKS} checks, {len(FAILURES)} failure(s), {len(WARNINGS)} warning(s)")
print("=" * 74)
for message in WARNINGS:
    print(f"  note: {message}")
if FAILURES:
    print("\nFAILURES:")
    for failure in FAILURES:
        print(f"  - {failure}")
    sys.exit(1)
print("\nALL WIRING CHECKS PASSED")
