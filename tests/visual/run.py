"""Render the dashboard card in every scenario and compare with the last release.

    python tests/visual/run.py            # the working tree → snapshots/current
    python tests/visual/run.py --release  # a new version  → snapshots/<version>

Runs in the Docker image of tests/visual/Dockerfile (make visual / make
visual-release), so fonts and rendering are the same on every machine. The
images and the report are not committed (.gitignore): snapshots keeps the last
KEEP_VERSIONS releases, and report/index.html shows what changed against the
newest of them, side by side with a diff.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MANIFEST = ROOT / "custom_components" / "greek_courier_tracker" / "manifest.json"
SNAPSHOTS = HERE / "snapshots"
REPORT = HERE / "report"
CURRENT = "current"
KEEP_VERSIONS = 3
THEMES = ("light", "dark")
# Keep in sync with NOW in scenarios.js
NOW = "2026-11-20T12:00:00+02:00"
VERSION = re.compile(r"^\d+(\.\d+)*$")


def version_key(name: str) -> tuple[int, ...]:
    return tuple(int(part) for part in name.split("."))


def released_versions() -> list[str]:
    """The versions with snapshots, oldest first."""
    if not SNAPSHOTS.is_dir():
        return []
    names = [path.name for path in SNAPSHOTS.iterdir() if path.is_dir() and VERSION.match(path.name)]
    return sorted(names, key=version_key)


def render(target: Path) -> list[str]:
    """Screenshot every scenario in both themes; return the file names."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    files = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 900, "height": 1600},
            device_scale_factor=1,
            locale="el-GR",
            timezone_id="Europe/Athens",
        )
        page = context.new_page()
        page.clock.set_fixed_time(NOW)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((HERE / "page.html").as_uri())
        names = page.evaluate("() => window.SCENARIOS.map((scenario) => scenario.name)")
        for name in names:
            for theme in THEMES:
                page.evaluate("([name, theme]) => window.renderScenario(name, theme)", [name, theme])
                file = f"{name}-{theme}.png"
                page.locator("#host").screenshot(path=str(target / file), animations="disabled")
                files.append(file)
        browser.close()
    if errors:
        print("The page reported errors:\n  " + "\n  ".join(errors), file=sys.stderr)
        sys.exit(1)
    return files


def compare(baseline: Path | None, target: Path) -> dict[str, list[str]]:
    """Sort the images into changed, new, removed and unchanged; draw the diffs."""
    if REPORT.exists():
        shutil.rmtree(REPORT)
    (REPORT / "diff").mkdir(parents=True)
    current = {path.name for path in target.glob("*.png")}
    previous = {path.name for path in baseline.glob("*.png")} if baseline else set()
    result = {
        "changed": [],
        "new": sorted(current - previous),
        "removed": sorted(previous - current),
        "unchanged": [],
    }
    for file in sorted(current & previous):
        before = Image.open(baseline / file).convert("RGB")
        after = Image.open(target / file).convert("RGB")
        if before.size == after.size and ImageChops.difference(before, after).getbbox() is None:
            result["unchanged"].append(file)
            continue
        result["changed"].append(file)
        if before.size == after.size:
            mask = ImageChops.difference(before, after).convert("L").point(lambda value: 255 if value else 0)
            faded = Image.blend(after.convert("L").convert("RGB"), Image.new("RGB", after.size, "white"), 0.6)
            faded.paste(Image.new("RGB", after.size, (230, 0, 0)), mask=mask)
            faded.save(REPORT / "diff" / file)
    return result


def write_report(result: dict[str, list[str]], baseline: Path | None, target: Path) -> Path:
    def image(folder: str, file: str) -> str:
        return f'<a href="{folder}/{file}"><img src="{folder}/{file}" loading="lazy"></a>'

    rel_target = f"../snapshots/{target.name}"
    rel_base = f"../snapshots/{baseline.name}" if baseline else ""
    sections = []
    for file in result["changed"]:
        diff = image("diff", file) if (REPORT / "diff" / file).exists() else "<p>Different size</p>"
        sections.append(
            f"<h3>{html.escape(file)}</h3><div class=row>"
            f"<figure>{image(rel_base, file)}<figcaption>{html.escape(baseline.name)}</figcaption></figure>"
            f"<figure>{image(rel_target, file)}<figcaption>{html.escape(target.name)}</figcaption></figure>"
            f"<figure>{diff}<figcaption>diff</figcaption></figure></div>"
        )
    new = "".join(
        f"<figure>{image(rel_target, file)}<figcaption>{html.escape(file)}</figcaption></figure>"
        for file in result["new"]
    )
    title = f"{target.name} against {baseline.name}" if baseline else f"{target.name} (no earlier version)"
    page = f"""<!doctype html><meta charset="utf-8"><title>Card changes</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#f4f4f4;color:#222}}
.row{{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}}
figure{{margin:0 0 16px;background:#fff;padding:8px;border-radius:8px}}
img{{max-width:560px;display:block}} figcaption{{font-size:12px;color:#666;margin-top:4px}}
.summary span{{margin-right:16px}}
</style>
<h1>Card: {html.escape(title)}</h1>
<p class=summary><span>Changed: {len(result["changed"])}</span><span>New: {len(result["new"])}</span>
<span>Removed: {len(result["removed"])}</span><span>Unchanged: {len(result["unchanged"])}</span></p>
<h2>Changed</h2>{"".join(sections) or "<p>None</p>"}
<h2>New</h2><div class=row>{new or "<p>None</p>"}</div>
<h2>Removed</h2><p>{html.escape(", ".join(result["removed"])) or "None"}</p>
"""
    path = REPORT / "index.html"
    path.write_text(page, encoding="utf-8")
    (REPORT / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", action="store_true", help="keep the images as the version in manifest.json")
    args = parser.parse_args()

    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    name = version if args.release else CURRENT
    earlier = [item for item in released_versions() if item != name]
    if args.release:
        earlier = [item for item in earlier if version_key(item) < version_key(version)]
    baseline = SNAPSHOTS / earlier[-1] if earlier else None

    target = SNAPSHOTS / name
    files = render(target)
    result = compare(baseline, target)
    report = write_report(result, baseline, target)

    if args.release:
        # The working copy images are now the release; keep only the latest releases
        shutil.rmtree(SNAPSHOTS / CURRENT, ignore_errors=True)
        for old in released_versions()[:-KEEP_VERSIONS]:
            shutil.rmtree(SNAPSHOTS / old)

    print(f"Rendered {len(files)} images into {target.relative_to(ROOT)}")
    print(f"Compared with: {baseline.name if baseline else 'nothing (first version)'}")
    for key in ("changed", "new", "removed"):
        if result[key]:
            print(f"{key.capitalize()} ({len(result[key])}): {', '.join(result[key])}")
    print(f"Unchanged: {len(result['unchanged'])}")
    print(f"Report: {report.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
