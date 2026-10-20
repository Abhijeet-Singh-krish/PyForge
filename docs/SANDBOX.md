# Disposable Python Sandbox Isolation (Defense in Depth)

Every learner submission is treated as untrusted, potentially malicious code:
1. **Layer 1 — Static AST Policy (`inspect_code_safety`)**: Blocks non-allowlisted imports (`os`, `sys`, `subprocess`, `socket`, `shutil`, `urllib`, `http`, `ctypes`, `multiprocessing`, `pty`), dangerous builtins (`open`, `eval`, `exec`, `compile`, `__import__`, `getattr`), dunder reflection escapes (`__subclasses__`, `__bases__`, `__globals__`), and exponentiation bombs (`999999 ** 999999`).
2. **Layer 2 — Ephemeral Workspace & Scrubbed Environment**: Each run spawns inside a `0700` temporary directory (`tempfile.TemporaryDirectory`) deleted immediately after execution, with an empty environment (`PATH=/usr/bin:/bin`, zero secrets or credentials).
3. **Layer 3 — Runtime Builtin Guard & OS Kernel Limits**: Pre-exec hooks set `RLIMIT_CPU=2s`, `RLIMIT_AS=64MB`, `RLIMIT_FSIZE=8KB`, `RLIMIT_NOFILE=16`, new process group session (`start_new_session=True`), wall-clock timeout with `os.killpg(SIGKILL)`, and 8 KB stdout/stderr truncation.
4. **Layer 4 — Container Isolation**: Production execution containers run with `network_mode: none`, `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges: true`, `pids_limit: 16`, and custom `seccomp_profile.json`.
