"""Explicit-file, reviewed-plan publisher. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {"README.md", "LICENSE", "AGENTS.md", "catalog.json", ".gitignore",
             ".gitattributes", "publish.cmd"}
TOP_DIRS = {"skills", "docs", "templates", "tools", ".github"}
BLOCKED_PARTS = {".git", ".local", "evals", "node_modules", "__pycache__", ".venv"}
TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml",
                 ".sh", ".ps1", ".cmd", ".csv", ".html", ".css", ".js", ".ts", ".svg"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SENSITIVE = [
    ("private home path", re.compile(r"(?i)[a-z]:[\\/]Users[\\/][^\s\\/]+|/(?:Users|home)/[a-zA-Z0-9_.-]+")),
    ("GitHub credential", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("API credential", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("credential assignment", re.compile(r'''(?im)^\s*(?:api_key|access_token|password|secret)\s*[:=]\s*["']?[A-Za-z0-9+/=_-]{16,}''')),
]


class Stop(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git(root, *args, check=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    p = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=90)
    if check and p.returncode:
        raise Stop(f"git {args[0]} failed: {p.stderr.strip() or p.stdout.strip()}")
    return p


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise Stop(f"Cannot read {path.name}: {exc}") from exc


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def safe_path(root, relative):
    p = PurePosixPath(relative)
    if not relative or "\\" in relative or p.is_absolute() or any(x in {".", ".."} for x in relative.split("/")):
        raise Stop(f"Unsafe relative path: {relative}")
    if any(x in BLOCKED_PARTS or x.startswith(".env") for x in p.parts):
        raise Stop(f"Private/generated path excluded: {relative}")
    if (len(p.parts) == 1 and relative not in TOP_FILES) or (len(p.parts) > 1 and p.parts[0] not in TOP_DIRS):
        raise Stop(f"Path outside public allowlist: {relative}")
    target = root.joinpath(*p.parts)
    for part in [target, *target.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise Stop(f"Link/junction not allowed: {relative}")
        # Windows Python 3.10/3.11: also reject directory reparse points.
        if part.exists() and getattr(part.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
            raise Stop(f"Reparse point not allowed: {relative}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise Stop(f"Path escaped repository: {relative}")
    return target


def public_files(root):
    p = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted(set(x for x in p.stdout.split("\0") if x))


def scalar(text, key):
    values = re.findall(r"^" + re.escape(key) + r":\s*(.*?)\s*$", text, re.M)
    if len(values) != 1 or not values[0] or values[0] in {"|", ">", "|-", ">-"}:
        raise Stop(f"SKILL.md requires one single-line {key}")
    value = values[0]
    if value.startswith('"'):
        try:
            result = json.loads(value)
        except ValueError as exc:
            raise Stop(f"Invalid quoted {key}") from exc
        if not isinstance(result, str):
            raise Stop(f"{key} must be a string")
        return result
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise Stop(f"Invalid quoted {key}")
        return value[1:-1].replace("''", "'")
    if ": " in value or " #" in value or value[0] in "[{&*!|>@`":
        raise Stop(f"Quote the {key} scalar using a JSON string")
    return value


def check_repo(root):
    files = public_files(root)
    texts = {}
    for relative in files:
        p = safe_path(root, relative)
        if not p.exists():  # Planned deletion is checked against catalog below.
            continue
        if not p.is_file() or p.stat().st_size > 1024 * 1024:
            raise Stop(f"Not a text file under 1 MiB: {relative}")
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in {"LICENSE", ".gitignore", ".gitattributes"}:
            raise Stop(f"File format needs explicit policy review: {relative}")
        try:
            text = p.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            raise Stop(f"Not UTF-8 text: {relative}") from exc
        if "\0" in text:
            raise Stop(f"Binary content: {relative}")
        for label, pattern in SENSITIVE:
            if pattern.search(text):
                raise Stop(f"Possible {label} in {relative}; inspect locally (matched text is not logged)")
        texts[relative] = text
    required = {"README.md", "LICENSE", "catalog.json", ".gitignore"}
    if required - texts.keys():
        raise Stop("Missing repository files: " + ", ".join(sorted(required - texts.keys())))
    catalog = load(root / "catalog.json")
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("skills"), list):
        raise Stop("catalog.json must have schema_version=1 and a skills list")
    names = set()
    for entry in catalog["skills"]:
        name = entry.get("name", "")
        if not isinstance(name, str) or not NAME.fullmatch(name) or len(name) > 64 or name in names:
            raise Stop("Invalid or duplicate catalog name")
        names.add(name)
        base = f"skills/{name}"
        if entry.get("path") != base or not re.fullmatch(r"\d+\.\d+\.\d+", entry.get("version", "")):
            raise Stop(f"Invalid path/version for {name}")
        if not entry.get("summary") or not entry.get("license"):
            raise Stop(f"Missing summary/license for {name}")
        validation = entry.get("validation", {})
        if validation.get("level") not in {"held-out-regression", "installed"} or not validation.get("summary"):
            raise Stop(f"Public Skill {name} needs an evidenced held-out/regression summary")
        for filename in ["SKILL.md", "README.md", "LICENSE"]:
            if f"{base}/{filename}" not in texts:
                raise Stop(f"Missing {base}/{filename}")
        skill = texts[f"{base}/SKILL.md"]
        front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", skill, re.S)
        if not front or scalar(front[1], "name") != name:
            raise Stop(f"Missing/mismatched frontmatter in {name}")
        if not 1 <= len(scalar(front[1], "description")) <= 1024:
            raise Stop(f"Description length invalid in {name}")
        if not skill[front.end():].strip():
            raise Stop(f"Empty Skill body: {name}")
        readme = texts[f"{base}/README.md"]
        for section in ["用途", "输入", "输出", "使用示例", "依赖", "边界", "验证", "许可"]:
            if not re.search(r"^#{1,6}\s+" + section + r"\s*$", readme, re.M):
                raise Stop(f"README missing {section}: {name}")
    for relative, text in texts.items():
        parts = PurePosixPath(relative).parts
        if parts[0] == "skills" and len(parts) > 2 and parts[1] not in names:
            raise Stop(f"Unregistered Skill content: {relative}")
        if relative.endswith("SKILL.md") and not (len(parts) == 3 and parts[0] == "skills" and parts[1] in names):
            raise Stop(f"Unexpected installable Skill file: {relative}")
        if relative.endswith(".md"):
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                target = target.split(' "', 1)[0].strip("<>")
                if not target or re.match(r"[a-zA-Z][\w+.-]*:", target) or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0]
                resolved = (root / relative).parent.joinpath(target).resolve()
                if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                    raise Stop(f"Missing/outside Markdown reference in {relative}: {target}")
                if resolved.is_file() and resolved.relative_to(root.resolve()).as_posix() not in texts:
                    raise Stop(f"Markdown reference points to unpublished file in {relative}")
    return {"files": len(texts), "skills": len(names)}


def ensure_repository(root):
    actual = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if actual != root.resolve():
        raise Stop("Use a dedicated Git repository, not a directory inside another repository")
    if git(root, "symbolic-ref", "--short", "HEAD").stdout.strip() != "main":
        raise Stop("Publishing requires the main branch")


def head(root):
    p = git(root, "rev-parse", "--verify", "HEAD", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def staged(root):
    return set(filter(None, git(root, "diff", "--cached", "--name-only", "--no-renames", "-z").stdout.split("\0")))


def changes(root):
    result = set(filter(None, git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0")))
    if head(root):
        result.update(filter(None, git(root, "diff", "HEAD", "--name-only", "--no-renames", "-z").stdout.split("\0")))
    else:
        result.update(filter(None, git(root, "ls-files", "--cached", "-z").stdout.split("\0")))
    return result


def configured_remote(root):
    cfg = load(root / ".local/config.json")
    repository = cfg.get("repository", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository):
        raise Stop("Configure the final GitHub owner/repository first")
    expected = f"https://github.com/{repository}.git"
    for args in [("remote", "get-url", "--all", "origin"), ("remote", "get-url", "--push", "--all", "origin")]:
        if git(root, *args).stdout.splitlines() != [expected]:
            raise Stop("origin fetch/push URL does not match the configured repository")
    return expected


def remote_head(root):
    output = git(root, "ls-remote", "origin", "refs/heads/main").stdout.strip()
    if not output:
        return None
    if not re.fullmatch(r"[0-9a-f]{40,64}\s+refs/heads/main", output):
        raise Stop("Unexpected remote branch response")
    return output.split()[0]


def file_state(root, relative):
    p = safe_path(root, relative)
    if not p.exists():
        return {"path": relative, "sha256": None, "blob": None, "action": "delete"}
    if not p.is_file():
        raise Stop(f"List individual files, not directories: {relative}")
    return {"path": relative, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "blob": git(root, "hash-object", f"--path={relative}", "--", relative).stdout.strip(),
            "action": "write"}


def create_plan(root, files, message):
    ensure_repository(root)
    if staged(root):
        raise Stop("Existing staged changes: review and clear the index first")
    target = configured_remote(root)
    baseline = head(root)
    if remote_head(root) != baseline:
        raise Stop("Local and remote main differ; synchronize deliberately before planning")
    wanted = sorted(set(files))
    if not wanted or set(wanted) != changes(root):
        raise Stop("Plan must exactly list all current changed/untracked public files")
    if not message.strip():
        raise Stop("A meaningful commit message is required")
    report = check_repo(root)
    plan = {"schema_version": 1, "created_at": now(), "target": target, "branch": "main",
            "base": baseline, "message": message, "files": [file_state(root, p) for p in wanted],
            "checks": report, "approval": None, "commit": None, "published_at": None}
    save(root / ".local/publish-plan.json", plan)
    return plan


def validate_plan(root, plan, require_approval=False):
    ensure_repository(root)
    if plan.get("schema_version") != 1 or plan.get("branch") != "main":
        raise Stop("Invalid plan")
    if plan["target"] != configured_remote(root):
        raise Stop("Remote target changed after planning")
    if require_approval and not plan.get("approval"):
        raise Stop("Plan is not approved; confirm its actual files before recording approval")
    if staged(root):
        raise Stop("Existing staged changes: publication stopped")
    check_repo(root)
    if head(root) != (plan.get("commit") or plan["base"]):
        raise Stop("Local HEAD changed after planning")
    expected_changes = set() if plan.get("commit") else {x["path"] for x in plan["files"]}
    if changes(root) != expected_changes:
        raise Stop("Changes outside plan or planned files no longer match")
    for item in plan["files"]:
        if file_state(root, item["path"]) != item:
            raise Stop(f"File changed after review: {item['path']}")


def approve(root, note):
    plan = load(root / ".local/publish-plan.json")
    validate_plan(root, plan)
    if not note.strip():
        raise Stop("Record the user's actual approval scope")
    plan["approval"] = {"at": now(), "note": note}
    save(root / ".local/publish-plan.json", plan)
    return plan


def verify_tree(root, ref, plan):
    for item in plan["files"]:
        p = git(root, "rev-parse", "--verify", f"{ref}:{item['path']}", check=False)
        value = p.stdout.strip() if p.returncode == 0 else None
        if value != item["blob"]:
            raise Stop(f"Staged/committed content differs from approval: {item['path']}")


def publish(root):
    lock = root / ".local/publish.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise Stop("Another publish is active; inspect any stale lock before removing it") from exc
    try:
        os.close(fd)
        plan = load(root / ".local/publish-plan.json")
        validate_plan(root, plan, require_approval=True)
        remote = remote_head(root)
        expected_heads = {plan["base"]}
        if plan.get("commit"):
            expected_heads.add(plan["commit"])
        if remote not in expected_heads:
            raise Stop("Remote changed after review; no force push is allowed")
        if not plan.get("commit"):
            for item in plan["files"]:
                git(root, "add", "--", item["path"])
            if staged(root) != {x["path"] for x in plan["files"]}:
                raise Stop("Staged scope differs from approval; inspect index before retrying")
            verify_tree(root, "", plan)
            message_file = root / ".local/commit-message.txt"
            message_file.write_text(plan["message"] + "\n", encoding="utf-8")
            git(root, "commit", "--file", str(message_file))
            commit = head(root)
            verify_tree(root, commit, plan)
            actual = set(filter(None, git(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z", commit).stdout.split("\0")))
            if actual != {x["path"] for x in plan["files"]} or changes(root):
                raise Stop("Commit hook or concurrent edit changed the approved scope; not pushed")
            plan["commit"] = commit
            save(root / ".local/publish-plan.json", plan)
        # Recheck the exact commit and worktree on retries as well.
        verify_tree(root, plan["commit"], plan)
        latest_remote = remote_head(root)
        if latest_remote not in {plan["base"], plan["commit"]}:
            raise Stop("Remote changed during publication; inspect before retrying")
        if latest_remote != plan["commit"]:
            git(root, "push", "origin", f"{plan['commit']}:refs/heads/main")
        if remote_head(root) != plan["commit"]:
            raise Stop("Could not verify the remote commit; retry after checking connectivity")
        plan["published_at"] = now()
        save(root / ".local/publish-plan.json", plan)
        return {"target": plan["target"], "commit": plan["commit"], "files": len(plan["files"])}
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    config = commands.add_parser("configure")
    config.add_argument("--repository", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--files", nargs="+", required=True)
    planning.add_argument("--message", required=True)
    approval = commands.add_parser("approve")
    approval.add_argument("--note", required=True)
    commands.add_parser("publish")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", args.repository):
                raise Stop("Expected owner/repository")
            save(ROOT / ".local/config.json", {"repository": args.repository})
            result = {"configured": args.repository}
        elif args.command == "check":
            result = check_repo(ROOT)
        elif args.command == "plan":
            result = create_plan(ROOT, args.files, args.message)
        elif args.command == "approve":
            plan = approve(ROOT, args.note)
            result = {"approved_files": len(plan["files"]), "target": plan["target"]}
        else:
            result = publish(ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Stop, subprocess.TimeoutExpired, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
