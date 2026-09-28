# Vendored wheels

Pinned neutral core used by this Skill only. Do not replace with a sibling Skill private package.

| File | Version | SHA-256 |
|---|---|---|
| `douyin_knowledge_core-0.2.1-py3-none-any.whl` | 0.2.1 | `8aa30c71c080793d9dceac702b1a28a330b5a1d70de89eb78b042a384ffbfe89` |

0.2.1 adds a Windows `msvcrt.locking` path for `profile_lock`. Unix still uses `fcntl.flock`.

Install (also pulled automatically by `pip install .` via pyproject file URL):

```bash
python -m pip install ./vendor/wheels/douyin_knowledge_core-0.2.1-py3-none-any.whl
```
