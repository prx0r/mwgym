"""LabWorkspace — one Git repo, worktrees per run.

Per spec §9:
  main lab repo
    └── .moltwork/worktrees/{run_id}
        git worktree add

NOT separate repos per run.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


def _git(args: list[str], cwd: str) -> tuple[int, str, str]:
    r = subprocess.run(["git"] + args, capture_output=True, text=True,
                       timeout=15, cwd=cwd)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


@dataclass
class LabWorkspace:
    """One lab repo with worktrees per run."""
    lab_dir: str = "/root/mwgym/lab"
    worktree_base: str = ".moltwork/worktrees"

    def ensure_lab(self) -> str:
        """Create main lab repo if needed. Returns lab dir."""
        p = Path(self.lab_dir)
        p.mkdir(parents=True, exist_ok=True)

        if not (p / ".git").exists():
            _git(["init"], self.lab_dir)
            _git(["config", "user.email", "mwgym@local"], self.lab_dir)
            _git(["config", "user.name", "MWGym"], self.lab_dir)
            (p / ".gitignore").write_text(
                f"{self.worktree_base}/\n__pycache__/\n*.pyc\n.env\n"
            )
            _git(["add", ".gitignore"], self.lab_dir)
            _git(["commit", "-m", "init: MWGym lab"], self.lab_dir)

            # Create directories
            (p / self.worktree_base).mkdir(parents=True, exist_ok=True)
            (p / "worlds").mkdir(exist_ok=True)
            (p / "runs").mkdir(exist_ok=True)
            _git(["add", "-A"], self.lab_dir)
            _git(["commit", "-m", "init: lab structure"], self.lab_dir)

        return self.lab_dir

    def create_run(self, run_id: str) -> RunWorktree:
        """Create a worktree for a run. Returns RunWorktree."""
        self.ensure_lab()
        wt = RunWorktree(lab=self, run_id=run_id)
        wt.create()
        return wt

    def current_head(self) -> str:
        code, out, _ = _git(["rev-parse", "HEAD"], self.lab_dir)
        return out if code == 0 else ""


@dataclass
class RunWorktree:
    """One run's worktree inside the lab repo."""
    lab: LabWorkspace
    run_id: str = ""
    path: str = ""
    branch: str = ""
    base_commit: str = ""   # B0
    final_commit: str = ""  # B1

    def create(self):
        """Create worktree with branch."""
        self.branch = f"mw/run/{self.run_id}"
        self.path = f"{self.lab.lab_dir}/{self.lab.worktree_base}/{self.run_id}"

        # Create branch if needed
        _git(["branch", self.branch], self.lab.lab_dir)
        # Create worktree
        Path(self.path).mkdir(parents=True, exist_ok=True)
        code, _, err = _git(["worktree", "add", self.path, self.branch],
                           self.lab.lab_dir)
        if code != 0:
            # Worktree might exist, try force
            _git(["worktree", "remove", self.path, "--force"], self.lab.lab_dir)
            _git(["worktree", "add", self.path, self.branch], self.lab.lab_dir)

        # Init git in worktree
        _git(["config", "user.email", "mwgym@local"], self.path)
        _git(["config", "user.name", "MWGym"], self.path)

        # Clean start
        (Path(self.path) / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\n")
        _git(["add", ".gitignore"], self.path)
        _git(["commit", "-m", f"init: run {self.run_id}"], self.path)

    def seed_world(self, files: dict[str, str], message: str = "world: initial state") -> str:
        """Write world files, commit as B0."""
        p = Path(self.path)
        for rel_path, content in files.items():
            fp = p / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)

        _git(["add", "-A"], self.path)
        _git(["commit", "-m", message], self.path)
        self.base_commit = self._head()
        return self.base_commit

    def commit_worker_output(self, message: str = "worker: solution") -> str:
        """Stage all + commit as B1."""
        _git(["add", "-A"], self.path)
        code, _, _ = _git(["commit", "-m", message], self.path)
        if code == 0:
            self.final_commit = self._head()
        return self.final_commit

    def diff(self) -> str:
        if self.base_commit:
            code, out, _ = _git(["diff", self.base_commit], self.path)
            return out if code == 0 else ""
        return ""

    def files_changed(self) -> list[str]:
        if self.base_commit:
            code, out, _ = _git(["diff", "--name-only", self.base_commit], self.path)
            return [f for f in out.split("\n") if f.strip()] if code == 0 else []
        return []

    def tree_hash(self) -> str:
        import hashlib as h
        digest = h.sha256()
        p = Path(self.path)
        for f in sorted(p.rglob("*")):
            if f.is_file() and ".git" not in str(f):
                digest.update(f.relative_to(p).as_posix().encode())
                digest.update(b"\0")
                digest.update(f.read_bytes())
                digest.update(b"\0")
        return digest.hexdigest()[:16]

    def _head(self) -> str:
        code, out, _ = _git(["rev-parse", "HEAD"], self.path)
        return out if code == 0 else ""

    def cleanup(self):
        """Remove worktree (keep branch)."""
        _git(["worktree", "remove", self.path, "--force"], self.lab.lab_dir)
