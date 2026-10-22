#!/usr/bin/env python3
"""Complete verification that the working tree is fully pushed to GitHub."""
import json
import os
import subprocess
import sys

TOKEN = open("/tmp/opencode/.gh-token").read().strip()
API = "https://api.github.com/repos/Pratyush-bit69/mathematica"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name +
          ("" if cond else "  — " + str(detail)))
    if not cond:
        fails.append(name)


def api(path):
    out = subprocess.check_output([
        "curl", "-sS", "-H", f"Authorization: Bearer {TOKEN}",
        "-H", "Accept: application/vnd.github+json", API + path])
    return json.loads(out)


print("=== 1. repository ===")
repo = api("")
check("repo exists", "full_name" in repo, repo.get("message"))
check("repo is PRIVATE", repo.get("private") is True)
check("default branch is main", repo.get("default_branch") == "main")
print(f"        {repo.get('full_name')}  —  {repo.get('html_url')}")

print("\n=== 2. working tree state ===")
dirty = subprocess.check_output(
    ["git", "-C", REPO, "status", "--porcelain"], text=True).strip()
check("no uncommitted changes", dirty == "", dirty[:200])
untracked = [l for l in dirty.splitlines() if l.startswith("??")]
check("no untracked files", not untracked, untracked[:10])
stashes = subprocess.check_output(["git", "-C", REPO, "stash", "list"], text=True).strip()
check("no stashes", stashes == "", stashes[:120])

print("\n=== 3. refs ===")
local_head = subprocess.check_output(
    ["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
remote = subprocess.check_output(
    ["git", "-C", REPO, "ls-remote", "origin"], text=True).strip().splitlines()
remote_heads = {l.split()[1]: l.split()[0] for l in remote if l.endswith("HEAD")}
remote_main = [l.split()[0] for l in remote if l.split()[1] == "refs/heads/main"]
check("origin/main == local HEAD",
      bool(remote_main) and remote_main[0] == local_head,
      f"remote={remote_main} local={local_head}")
print(f"        local  {local_head}")
print(f"        remote {remote_main[0] if remote_main else '?'}")

print("\n=== 4. tree comparison (blob SHAs) ===")
tree = api("/git/trees/main?recursive=1")
if "tree" not in tree:
    check("tree readable", False, tree.get("message"))
else:
    rem = {e["path"]: e["sha"] for e in tree["tree"] if e["type"] == "blob"}
    loc = {}
    for line in subprocess.check_output(
            ["git", "-C", REPO, "ls-files", "-s"], text=True).splitlines():
        meta, path = line.split("\t", 1)
        loc[path] = meta.split()[1]
    missing = sorted(set(loc) - set(rem))
    extra = sorted(set(rem) - set(loc))
    differ = sorted(p for p in set(loc) & set(rem) if loc[p] != rem[p])
    check("every local file is on the remote", not missing,
          f"{len(missing)} missing: {missing[:6]}")
    check("no stray remote files", not extra,
          f"{len(extra)} extra: {extra[:6]}")
    check("every file is byte-identical", not differ,
          f"{len(differ)} differ: {differ[:6]}")
    print(f"        {len(loc)} files, {len(rem)} on remote, "
          f"{len(differ)} content mismatches")

    print("\n=== 5. key assets present on the remote ===")
    must = ["index.html", "reader.html", "lab.html", "glossary.html",
            "README.md", ".gitignore",
            "assets/css/main.css", "assets/js/app.js", "assets/js/home.js",
            "assets/js/reader.js", "assets/js/lab.js", "assets/js/expr.js",
            "assets/js/glossary.js", "assets/data/treatise.js",
            "assets/data/glossary.js", "assets/katex/katex.min.js",
            "assets/katex/katex.min.css", "assets/fonts/fonts.css"]
    absent = [p for p in must if p not in rem]
    check("all key files present", not absent, absent)
    # fonts + katex font binaries
    fonts = [p for p in rem if p.endswith(".woff2")]
    katexfonts = [p for p in rem if p.startswith("assets/katex/fonts/")]
    check("web fonts committed", len(fonts) >= 8, f"{len(fonts)} woff2 files")
    check("KaTeX font binaries committed", len(katexfonts) >= 15,
          f"{len(katexfonts)} files")

print("\n=== 6. commit history ===")
commits = api("/commits?per_page=20")
for c in commits[:5]:
    print(f"        {c['sha'][:8]}  {c['commit']['author']['date']}  "
          f"{c['commit']['message'].splitlines()[0][:60]}")
check("history is on the remote", len(commits) >= 2, len(commits))

print("\n=== 7. GitHub Pages ===")
pg = api("/pages")
check("Pages enabled", "html_url" in pg, pg.get("message"))
print(f"        {pg.get('html_url')}  (https_enforced={pg.get('https_enforced')})")
build = api("/pages/builds/latest")
check("latest build succeeded", build.get("status") == "built", build.get("status"))
check("deployed commit == local HEAD",
      build.get("commit", "")[:40] == local_head,
      f"built={build.get('commit')} local={local_head}")
print(f"        built {build.get('commit','')[:8]} at {build.get('updated_at')}")

print("\n=== 8. live site ===")
import urllib.request
for path, expect in [("/", "MATHEMATICA"), ("/reader.html", "Reader"),
                     ("/lab.html", "Lab"), ("/glossary.html", "Glossary")]:
    url = (pg.get("html_url") or "").rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
            ok = r.status == 200 and expect.lower() in body.lower()
            check(f"live {path}", ok, r.status)
    except Exception as e:
        check(f"live {path}", False, e)
try:
    with urllib.request.urlopen((pg.get("html_url") or "").rstrip("/")
                                + "/assets/data/treatise.js", timeout=90) as r:
        n = len(r.read())
    check("live treatise.js complete", n == 1712487, f"{n} bytes")
except Exception as e:
    check("live treatise.js complete", False, e)

print()
print("ALL VERIFIED" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(0 if not fails else 1)
