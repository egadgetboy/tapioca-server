"""The release workflow's own script (.github/workflows/release.yml), run
with stand-ins for gh, docker, skopeo and ssh-keygen, in a git repository
of its own.

Releases are source only (the owner, October 12): a version whose tests
passed is published with its zip, tapioca-server.yaml (stationplay.yaml
before 1.35.0), docker-compose.yml and
the list of packages in the image that was tested, made by a run that
passed (the image workflow's "Made of" step, read here for the artifact's
name and file). No image is built, pushed or pulled, and nothing is
published without that list, without passed tests, or twice. One version
that can't be published never stops the next (the audit of 1.32.1).

From 1.34.0 (the owner, October 12, later the same day: D4 is No, U1), the
image is published too: the very one the image workflow tested, by digest,
gets the version's tags (C7), and the release carries the arm64 image's
package list, the source of the images' GPL and LGPL packages (C6), and the
zip's signature, which is required from 1.35.0. Versions before 1.34.0
publish as they did.

The audit of 1.34.0: each release is made as a draft, its image's tags
moved only then, and published once anyone can pull its image (a draft
left from a run before is deleted first, and never counts as published);
SHA256SUMS lists every file and the image's digest by its version's tag, signed
like the zip; a version's tests passed only when both machines' Test steps
did (the real jq, on GitHub's answers); the signing key is on disk only
while signing; and the job runs only in tapiOca's own repository, with
no credentials left in the checkout.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
IMAGE = ROOT / ".github" / "workflows" / "image.yml"

# Stand-ins: each logs what it was asked (and whether the signing key was on
# disk then), and answers from files the test writes in $ASSETS: published
# and drafts (the releases out, and drafts, by tag), runs.json (the image
# workflow's runs, as GitHub lists them), jobs_<run>.json (that run's jobs
# and their steps, as GitHub answers) and made_<run>/ (the files that run
# kept, under the artifact's name, $ARTIFACT, which the test reads from
# image.yml). gh answers --jq with the real jq, as gh does.
KEY_ON_DISK = """[ -e "$RUNNER_TEMP/signing-key" ] && echo "KEY ON DISK, asked: $*" >> "$LOG"
"""
GH = """#!/bin/bash
echo "gh $*" >> "$LOG"
@KEY_ON_DISK@
filter="." prev=""
for a in "$@"; do [ "$prev" = --jq ] && filter=$a; prev=$a; done
answer() { if [ -e "$1" ]; then jq -r "$filter" "$1"; fi; }
case "$1 $2" in
  "release list")
    { sed 's/.*/{"tagName": "&", "isDraft": false}/' "$ASSETS/published" 2>/dev/null
      sed 's/.*/{"tagName": "&", "isDraft": true}/' "$ASSETS/drafts" 2>/dev/null
    } | jq -s . > "$ASSETS/releases.json"
    answer "$ASSETS/releases.json" ;;
  "api repos/"*/releases/tags/*) answer "$ASSETS/release_${2##*/}.json" ;;
  "api repos/"*/workflows/*) answer "$ASSETS/runs.json" ;;
  "api repos/"*/jobs)
    run=$(sed 's|.*/runs/\\([0-9]*\\)/jobs|\\1|' <<< "$2")
    answer "$ASSETS/jobs_$run.json" ;;
  "run download")
    # (gh run download <run> --name <artifact> --dir <folder>)
    [ "$4 $5 $6" = "--name $ARTIFACT --dir" ] || exit 2
    [ -d "$ASSETS/made_$3" ] || exit 1
    mkdir -p "$7" && cp "$ASSETS/made_$3"/* "$7/" ;;
  *) exit 0 ;;
esac
""".replace("@KEY_ON_DISK@\n", KEY_ON_DISK)
DOCKER = """#!/bin/bash
echo "docker $*" >> "$LOG"
@KEY_ON_DISK@
# (Fetching the source: a file in the folder mounted at /out, unless the
# test says it can't be had.)
if [ "$1" = run ]; then
  for a in "$@"; do
    case "$a" in
      *:/out) [ -e "$ASSETS/no_source" ] && exit 1
              mkdir -p "${a%:/out}" && echo source > "${a%:/out}/ffmpeg_7.1.5-0+deb13u1.dsc" ;;
    esac
  done
fi
[ "$1" = run ] || [ "$1" = login ] && cat > /dev/null
exit 0
""".replace("@KEY_ON_DISK@\n", KEY_ON_DISK)
# (The registry: what a tag holds now is $ASSETS/manifest; with
# $ASSETS/private, nothing can be pulled without signing in.)
SKOPEO = """#!/bin/bash
echo "skopeo $*" >> "$LOG"
@KEY_ON_DISK@
case "$1" in
  login) cat > /dev/null ;;
  inspect)
    if [ "$2" = --no-creds ]; then
      [ -e "$ASSETS/private" ] && { echo "unauthorized: authentication required" >&2; exit 1; }
      echo '{"Name": "ghcr.io/egadgetboy/tapioca-server"}'
    else
      cat "$ASSETS/manifest"
    fi ;;
esac
exit 0
""".replace("@KEY_ON_DISK@\n", KEY_ON_DISK)
# (Signing: the .sig beside the file, unless the test says the key won't do;
# and whether the key was on disk to sign with.)
SSH_KEYGEN = """#!/bin/bash
echo "ssh-keygen $*" >> "$LOG"
if [ "$2" = sign ]; then
  [ -s "$RUNNER_TEMP/signing-key" ] && echo "the key, there to sign ${@: -1}" >> "$LOG"
fi
[ -e "$ASSETS/key_wont_do" ] && exit 1
if [ "$2" = sign ]; then echo signature > "${@: -1}.sig"; fi
exit 0
"""
MANIFEST = "the two tested images, joined\n"


def script() -> str:
    """The "Publish what's new" step's script."""
    lines = WORKFLOW.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "name: Publish what's new" in line)
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run + 1]) - len(lines[run + 1].lstrip())
    body = []
    for line in lines[run + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body) + "\n"


def made_of() -> tuple[str, str]:
    """What image.yml keeps for release.yml: the artifact's name, and the
    package list's file name, with <version> for the version."""
    text = IMAGE.read_text()
    upload = re.search(
        r"uses: actions/upload-artifact@\S+\n\s+with:\n\s+name: (\S+)\n\s+path: (.+)\n", text
    )
    assert upload, "image.yml keeps the package list as an artifact"
    name, path = upload.groups()
    assert path == "${{ runner.temp }}/made/"
    made = re.search(r'> "\$RUNNER_TEMP/made/(tapioca-\$version-packages\.txt)"', text)
    assert made, "image.yml writes the package list into that folder"
    return name, made.group(1).replace("$version", "<version>")


def git(work: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=work, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


@pytest.fixture
def run(tmp_path):
    """The script, in a repository where 1.32.0 is out and 1.32.1's commit
    has its notes on top: the log of what gh and docker were asked, the
    exit status and what it said. `run.commits` has each version's commit;
    `run.version("1.32.2")` adds another version, with its notes."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, text in (("gh", GH), ("docker", DOCKER), ("skopeo", SKOPEO),
                       ("ssh-keygen", SSH_KEYGEN)):  # fmt: skip
        (bin_ / name).write_text(text)
        (bin_ / name).chmod((bin_ / name).stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "work"
    (work / "app").mkdir(parents=True)
    (work / "docs" / "releases").mkdir(parents=True)
    git(work, "init", "-q", "-b", "main")
    (work / "stationplay.yaml").write_text("services: {}\n")
    (work / "docker-compose.yml").write_text("services: {}\n")
    (work / "tools").mkdir()
    (work / "tools" / "gpl_source.py").write_text("# (a stand-in: the image runs it)\n")
    # (The release gate itself: it reads each version's manifest at its tested commit.)
    shutil.copy(Path(__file__).resolve().parents[1] / "tools" / "release_gate.py", work / "tools")
    (work / "docs" / "releases" / "v1.32.0.md").write_text("---\ncommit: x\n---\n")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "published").write_text("v1.32.0\n")
    log = tmp_path / "log"
    (tmp_path / "temp").mkdir()
    artifact, listed = made_of()
    commits: dict[str, str] = {}

    def version(number: str) -> str:
        (work / "app" / "__init__.py").write_text(f'__version__ = "{number}"\n')
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", f"tapiOca {number}")
        commits[number] = git(work, "rev-parse", "HEAD")
        notes = work / "docs" / "releases" / f"v{number}.md"
        notes.write_text(f"---\ncommit: {commits[number]}\n---\n\nThe notes.\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", f"Release notes for {number}")
        git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
        return commits[number]

    version("1.32.1")

    def go(**extra: str) -> tuple[str, int, str]:
        env = {
            **os.environ,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "LOG": str(log),
            "ASSETS": str(assets),
            "ARTIFACT": artifact,
            "RUNNER_TEMP": str(tmp_path / "temp"),
            "GITHUB_REPOSITORY": "egadgetboy/tapioca-server",
            "GITHUB_REPOSITORY_OWNER": "EgadgetBoy",
            "GH_TOKEN": "x",
            "FIRST_PUBLIC": "1.32.0",
            "FIRST_IMAGE": "1.34.0",
            "FIRST_SIGNED": "1.34.0",
            "FIRST_GATED": "1.44.2",
            "GITHUB_ACTOR": "egadgetboy",
            **extra,
        }
        done = subprocess.run(
            ["bash", "-e", "-c", script()], cwd=work, env=env, capture_output=True, text=True
        )
        return (log.read_text() if log.exists() else ""), done.returncode, done.stdout

    go.assets = assets  # type: ignore[attr-defined]
    go.commits = commits  # type: ignore[attr-defined]
    go.version = version  # type: ignore[attr-defined]
    go.listed = listed  # type: ignore[attr-defined]
    go.temp = tmp_path / "temp"  # type: ignore[attr-defined]
    go.work = work  # type: ignore[attr-defined]
    return go


def image_run(
    run, number: int, version: str = "1.32.1", status: str = "completed",
    test: str | tuple[str | None, ...] = "success", made: bool = True, image: bool = True,
) -> None:  # fmt: skip
    """Image run `number`, on that version's commit (newest first, as
    GitHub lists them: add the oldest first), its Test step's conclusion on
    each machine (`test`: one for both, or one each; None: that machine's
    job has no Test step, as when it's cancelled before it starts). From
    1.34.0, with what its image job kept too (`image`): the joined image, by
    digest, and the arm64 image's package list."""
    runs = run.assets / "runs.json"
    before = json.loads(runs.read_text())["workflow_runs"] if runs.exists() else []
    this = {"head_sha": run.commits[version], "id": number, "status": status}
    runs.write_text(json.dumps({"workflow_runs": [this, *before]}))
    each = (test, test) if isinstance(test, str) else test
    jobs = [
        {"name": "image", "steps": [{"name": "Join the tested images", "conclusion": "success"}]}
    ]
    for arch, conclusion in zip(("amd64", "arm64", "riscv64"), each, strict=False):
        steps = [{"name": "Build", "conclusion": "success"}]
        if conclusion is not None:
            steps.append({"name": "Test", "conclusion": conclusion})
        jobs.append({"name": f"build-and-test ({arch})", "steps": steps})
    (run.assets / f"jobs_{number}.json").write_text(json.dumps({"jobs": jobs}))
    if made:
        folder = run.assets / f"made_{number}"
        folder.mkdir()
        (folder / run.listed.replace("<version>", version)).write_text(
            f"tapiOca {version}: every package in the image that was tested\n"
        )
        if image:
            (folder / f"tapioca-{version}-image.txt").write_text(PINNED + "\n")
            (folder / f"tapioca-{version}-packages-arm64.txt").write_text(
                f"tapiOca {version}: every package in the arm64 image that was tested\n"
            )
    (run.assets / "manifest").write_text(MANIFEST)


def docker(said: str) -> list[str]:
    return [line for line in said.splitlines() if line.startswith("docker ")]


def creates(said: str) -> list[str]:
    return [line for line in said.splitlines() if line.startswith("gh release create")]


def publishes(said: str) -> list[str]:
    """Each draft made a release (published)."""
    return [
        line for line in said.splitlines()
        if line.startswith("gh release edit") and "--draft=false" in line
    ]  # fmt: skip


def test_a_tested_version_is_published_with_its_tested_package_list(run):
    image_run(run, 7)
    said, status, out = run()
    assert status == 0, said + out
    made = creates(said)
    assert len(made) == 1, said
    assert f"v1.32.1 --target {run.commits['1.32.1']}" in made[0]
    for name in (
        "tapioca-1.32.1.zip",
        "stationplay.yaml",
        "docker-compose.yml",
        "tapioca-1.32.1-packages.txt",
    ):
        assert f"/{name}" in made[0], made[0]
    assert "gh run download 7 --name" in said  # (a run that tested it)
    listed = run.temp / "v1.32.1" / "tapioca-1.32.1-packages.txt"
    assert listed.read_text() == "tapiOca 1.32.1: every package in the image that was tested\n"
    # (Source only: no image built, pushed or pulled, and no image's source.)
    assert not docker(said) and "ghcr" not in said and "gpl-source" not in said


def test_without_its_tested_package_list_nothing_is_published(run):
    image_run(run, 7, made=False)
    said, status, out = run()
    assert status == 1
    assert not creates(said)
    assert "has its list of packages" in out and "Re-run the newest of those runs" in out


def test_the_newest_passing_run_without_its_list_is_passed_over(run):
    """(A newer run on the same code that passed, but kept no list: one
    that did is used.)"""
    image_run(run, 7)
    image_run(run, 9, made=False)
    said, status, out = run()
    assert status == 0, said + out
    assert "gh run download 9" in said and "gh run download 7" in said
    assert len(creates(said)) == 1


def test_one_version_that_can_t_be_published_doesn_t_stop_the_next(run):
    run.version("1.32.2")
    image_run(run, 7, version="1.32.1", made=False)
    image_run(run, 8, version="1.32.2")
    said, status, _ = run()
    assert status == 1  # (1.32.1 refused, said on the run's page)
    made = creates(said)
    assert len(made) == 1 and made[0].startswith("gh release create v1.32.2 "), said
    [out] = publishes(said)
    assert out.startswith("gh release edit v1.32.2 ") and "--latest=true" in out


def test_a_version_whose_tests_failed_isn_t_published(run):
    image_run(run, 7, test="failure")
    said, status, out = run()
    assert status == 1
    assert not creates(said) and "run download" not in said
    assert "its tests didn't pass" in out


def test_a_version_still_being_tested_waits(run):
    image_run(run, 7, status="in_progress")
    said, status, out = run()
    assert status == 0
    assert not creates(said)
    assert "waits for its tests" in out


def test_a_published_release_is_left_alone(run):
    image_run(run, 7)
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    said, status, out = run()
    assert status == 0, said + out
    assert not creates(said)
    assert "release upload" not in said and "run download" not in said and not docker(said)


def test_the_artifact_release_yml_asks_for_is_the_one_image_yml_keeps():
    """(The audit of 1.32.1: renaming one without the other would refuse
    every release, with every other test still passing.)"""
    name, listed = made_of()
    text = WORKFLOW.read_text()
    assert f'--name {name} --dir "$out/made-$run"' in text
    assert listed.replace("<version>", "$version") in text


# From 1.34.0: the image, the sources and the signature -------------------------------------

DIGEST = "sha256:" + hashlib.sha256(MANIFEST.encode()).hexdigest()
PINNED = f"ghcr.io/egadgetboy/tapioca-server@{DIGEST}"


def skopeo(said: str) -> list[str]:
    return [line for line in said.splitlines() if line.startswith("skopeo copy")]


def test_from_1_34_0_the_tested_image_gets_its_tags(run):
    run.version("1.34.0")
    image_run(run, 7, version="1.32.1", image=False)
    image_run(run, 8, version="1.34.0")
    said, status, out = run(SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert status == 0, said + out
    # That very image (by digest), copied as it is, each tag checked.
    assert skopeo(said) == [
        f"skopeo copy --all --preserve-digests --quiet docker://{PINNED} "
        f"docker://ghcr.io/egadgetboy/tapioca-server:{tag}"
        for tag in ("1.34.0", "1.34", "latest")
    ]
    assert said.count("skopeo inspect --raw") == 3 and "docker build" not in said
    made = [line for line in creates(said) if line.startswith("gh release create v1.34.0 ")]
    assert len(made) == 1, said
    for name in ("tapioca-1.34.0-packages.txt", "tapioca-1.34.0-packages-arm64.txt",
                 "tapioca-1.34.0-source.tar", "tapioca-1.34.0.zip"):  # fmt: skip
        assert f"/{name}" in made[0], made[0]
    # The source, fetched in the tested image, with the arm64 image's list.
    [fetch] = [line for line in said.splitlines() if line.startswith("docker run")]
    assert PINNED in fetch and "--all --also /in/arm64.txt" in fetch and "--user 0" in fetch
    with tarfile.open(run.temp / "v1.34.0" / "tapioca-1.34.0-source.tar") as tar:
        assert "./ffmpeg_7.1.5-0+deb13u1.dsc" in tar.getnames()
    # Signed, from 1.34.0 (the 1.34.0 audit: SHA256SUMS ties the release to its image).
    assert "tapioca-1.34.0.zip.sig" in made[0] and "SHA256SUMS.sig" in made[0]
    # 1.32.1, before 1.34.0, as before: no image, no source.
    old = [line for line in creates(said) if line.startswith("gh release create v1.32.1 ")]
    assert len(old) == 1 and "source.tar" not in old[0] and "arm64" not in old[0]


def test_an_older_version_never_takes_the_newer_ones_tags(run):
    run.version("1.34.0")
    run.version("1.34.1")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0")
    image_run(run, 9, version="1.34.1")
    said, status, out = run(
        SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"
    )  # (signed from 1.34.0)
    assert status == 0, said + out
    tags = [line.rsplit(":", 1)[1] for line in skopeo(said)]
    assert tags == ["1.34.0", "1.34.1", "1.34", "latest"]


def test_signed_with_the_key_and_checked(run):
    run.version("1.35.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.35.0")
    said, status, out = run(SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert status == 0, said + out
    assert "ssh-keygen -Y sign -q -f" in said and "-n tapioca-release" in said
    assert "ssh-keygen -Y verify -f" in said and "-I tapioca-release" in said
    [made] = creates(said)
    assert "/tapioca-1.35.0.zip.sig" in made
    # (The key is gone once it's done.)
    assert not (run.temp / "signing-key").exists()


def test_from_1_35_0_an_unsigned_zip_isn_t_published(run):
    run.version("1.35.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.35.0")
    said, status, out = run()
    assert status == 1 and not creates(said) and not skopeo(said)
    assert "couldn't be signed" in out
    (run.assets / "key_wont_do").write_text("")
    said, status, out = run(SIGNING_KEY="a key with a passphrase")
    assert status == 1 and not creates(said) and "couldn't be signed" in out


def test_an_image_that_isn_t_the_tested_one_stops_it(run):
    run.version("1.34.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0")
    (run.assets / "manifest").write_text("something else\n")
    said, status, out = run(
        SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"
    )  # (signed from 1.34.0)
    assert status == 1 and not publishes(said)  # (its draft stays a draft)
    assert "isn't the image that was tested" in out


def test_without_its_image_or_its_sources_nothing_is_published(run):
    run.version("1.34.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0", image=False)
    said, status, out = run()
    assert status == 1 and not creates(said) and "kept no image" in out
    image_run(run, 9, version="1.34.0")
    (run.assets / "no_source").write_text("")
    said, status, out = run()
    assert status == 1 and not creates(said) and not skopeo(said)
    assert "GPL and LGPL packages couldn't all be fetched" in out


# The audit of 1.34.0 ---------------------------------------------------------------------------


def at(said: str, start: str) -> int:
    """Where the first line starting `start` is in the log."""
    lines = said.splitlines()
    return next(n for n, line in enumerate(lines) if line.startswith(start))


def test_a_draft_first_then_its_tags_then_its_published(run):
    """Each release is made a draft first; only then are its image's tags
    copied, and it's published once its image can be pulled by anyone."""
    run.version("1.34.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0")
    said, status, out = run(
        SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"
    )  # (signed from 1.34.0)
    assert status == 0, said + out
    [draft] = creates(said)
    assert draft.startswith("gh release create v1.34.0 ") and " --draft " in draft
    assert "--latest" not in draft  # (a draft can't be the latest release)
    [published] = publishes(said)
    assert published == "gh release edit v1.34.0 --draft=false --latest=true"
    anyone = f"skopeo inspect --no-creds --raw docker://{PINNED}"
    assert anyone in said.splitlines()
    assert (at(said, anyone) < at(said, "gh release create") < at(said, "skopeo copy")
            < at(said, "gh release edit"))  # fmt: skip


def test_a_draft_left_over_is_deleted_and_never_counts_as_published(run):
    """(A run that stopped after making its draft: the next one deletes it
    and makes the release again, rather than taking the version as out, or
    being stopped by it.)"""
    (run.assets / "drafts").write_text("v1.32.1\nv1.32.1\n")
    image_run(run, 7)
    said, status, out = run()
    assert status == 0, said + out
    assert "already published" not in out.replace("v1.32.0: already published", "")
    assert said.count("gh release delete v1.32.1 --yes") == 2
    assert at(said, "gh release delete v1.32.1") < at(said, "gh release create v1.32.1")
    assert len(publishes(said)) == 1
    # A published one is never deleted.
    (run.assets / "drafts").write_text("")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    again, status, _ = run()
    assert status == 0 and "release delete" not in again[len(said) :]


def test_an_image_only_signed_in_people_can_pull_isn_t_published(run):
    run.version("1.34.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0")
    (run.assets / "private").write_text("")
    said, status, out = run(SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert status == 1 and not publishes(said)
    # Checked before anything moves (the 1.34.0 audit: the tags had moved,
    # :latest included, before a private package was found): no tag copied,
    # no draft made.
    assert not skopeo(said) and not creates(said)
    assert ("v1.34.0 isn't published: its image can't be pulled without signing in to GitHub. "
            "tapiOca's package must be public") in out  # fmt: skip
    assert not re.search(r"\b(401|403)\b", out)


def test_sha256sums_lists_the_image_for_each_tag_and_every_file_signed(run):
    run.version("1.35.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.35.0")
    said, status, out = run(SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert status == 0, said + out
    folder = run.temp / "v1.35.0"
    names = ["tapioca-1.35.0.zip", "stationplay.yaml", "docker-compose.yml",
             "tapioca-1.35.0-packages.txt", "tapioca-1.35.0-packages-arm64.txt",
             "tapioca-1.35.0-source.tar"]  # fmt: skip
    lines = (folder / "SHA256SUMS").read_text().splitlines()
    for name in names:
        assert f"{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}" in lines
    # The image by its own version's tag only: :1.35 and :latest move with
    # later releases, so a signed line for them would go stale (the 1.34.0 audit).
    assert f"{DIGEST.removeprefix('sha256:')}  ghcr.io/egadgetboy/tapioca-server:1.35.0" in lines
    assert len(lines) == len(names) + 1
    # Signed as the zip is, and both with the release.
    assert f"-n tapioca-release {folder / 'SHA256SUMS'}" in said
    [draft] = creates(said)
    for name in ("SHA256SUMS", "SHA256SUMS.sig", "tapioca-1.35.0.zip.sig"):
        assert f"/{name}" in draft, draft


def test_the_truenas_file_is_published_by_the_name_its_commit_gives_it(run):
    """(The owner, October 13) From 1.35.0 the TrueNAS app file is
    tapioca-server.yaml: a version whose commit has it is published with it,
    and one before that keeps stationplay.yaml, its own commit's name."""
    git(run.work, "mv", "stationplay.yaml", "tapioca-server.yaml")
    run.version("1.35.0")
    image_run(run, 8, version="1.35.0")
    image_run(run, 7)
    said, status, out = run(SIGNING_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert status == 0, said + out
    made = {line.split()[3]: line for line in creates(said)}
    assert "/tapioca-server.yaml" in made["v1.35.0"] and "stationplay.yaml" not in made["v1.35.0"]
    assert "/stationplay.yaml" in made["v1.32.1"] and "tapioca-server" not in made["v1.32.1"]
    sums = (run.temp / "v1.35.0" / "SHA256SUMS").read_text()
    assert "  tapioca-server.yaml\n" in sums and "stationplay.yaml" not in sums


def test_sha256sums_comes_with_every_release(run):
    """(Before 1.34.0's image, its files only; unsigned before 1.35.0
    without a key, as the zip is.)"""
    image_run(run, 7)
    said, status, out = run()
    assert status == 0, said + out
    [draft] = creates(said)
    assert "/SHA256SUMS" in draft and "SHA256SUMS.sig" not in draft
    sums = (run.temp / "v1.32.1" / "SHA256SUMS").read_text()
    assert "tapioca-1.32.1.zip" in sums and "ghcr.io" not in sums


@pytest.mark.parametrize(
    ("each", "passed"),
    [
        (("success", "success"), True),
        (("success", "cancelled"), False),
        (("cancelled", "success"), False),
        (("success", "skipped"), False),
        (("success", None), False),  # (one machine's job never reached it)
        ((None, None), False),
        (("success",), False),  # (one machine missing)
        (("success", "success", "success"), False),  # (not exactly the two)
    ],
)
def test_both_machines_test_steps_must_pass(run, each, passed):
    """Read with the real jq, from GitHub's answer for a run's jobs."""
    image_run(run, 7, test=each)
    said, status, out = run()
    assert bool(publishes(said)) is passed, out
    assert status == (0 if passed else 1)
    if not passed:
        assert "its tests didn't pass (image run 7)" in out and "run download" not in said


def test_the_signing_key_is_on_disk_only_while_signing(run):
    run.version("1.35.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.35.0")
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"
    said, status, out = run(SIGNING_KEY=key)
    assert status == 0, said + out
    assert "the key, there to sign" in said and "KEY ON DISK" not in said
    assert not (run.temp / "signing-key").exists()
    # A key that won't do: gone all the same.
    (run.assets / "key_wont_do").write_text("")
    said, status, out = run(SIGNING_KEY=key)
    assert status == 1 and "KEY ON DISK" not in said
    assert not (run.temp / "signing-key").exists()


def test_the_job_runs_only_in_stationplay_s_repository_with_no_credentials_kept():
    text = WORKFLOW.read_text()
    job = text[text.index("  publish:\n") :]
    assert re.search(r"^    if: github\.repository == 'egadgetboy/tapioca-server'$", job, re.M)
    checkout = re.search(r"- uses: actions/checkout@\S+\n((?:\s{8,}\S.*\n)+)", job)
    assert checkout and re.search(r"^\s+persist-credentials: false$", checkout.group(1), re.M)
    # (No environment: making one changes the repository's settings, which
    # only the owner does.)
    assert not re.search(r"^\s+environment:", text, re.M)


def test_from_1_34_0_a_release_is_never_published_unsigned(run):
    """(The 1.34.0 audit: without the key, 1.34.0 went out unsigned, with a
    warning only; its SHA256SUMS is what ties it to its image.)"""
    run.version("1.34.0")
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    image_run(run, 8, version="1.34.0")
    said, status, out = run()
    assert status == 1 and not publishes(said) and not skopeo(said)
    assert "v1.34.0 isn't published: its zip and SHA256SUMS couldn't be signed" in out


def test_the_workflow_signs_from_1_34_0():
    text = (ROOT / ".github/workflows/release.yml").read_text()
    assert 'FIRST_SIGNED: "1.34.0"' in text


def test_every_file_release_yml_reads_is_one_image_yml_writes():
    """(The 1.34.0 audit: renaming the image's reference or the arm64 list in
    image.yml would have stopped every release, with every test passing.)"""
    reads = set(
        re.findall(r'\$(?:made|out/made-\$run)/(tapioca-\$version-[\w.-]+)"', WORKFLOW.read_text())
    )
    writes = set(re.findall(r'"\$RUNNER_TEMP/made/(tapioca-\$version-[\w.-]+)"', IMAGE.read_text()))
    assert reads >= {"tapioca-$version-image.txt", "tapioca-$version-packages.txt",
                     "tapioca-$version-packages-arm64.txt"}, reads  # fmt: skip
    assert reads <= writes, (
        f"release.yml reads {sorted(reads - writes)}, which image.yml never writes"
    )


def test_no_workflow_leaves_its_credentials_in_a_checkout():
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = path.read_text()
        for found in re.finditer(r"uses: actions/checkout@\S+\n((?:\s{8,}.*\n)*)", text):
            assert "persist-credentials: false" in found.group(1), f"{path.name}: {found.group(0)}"


# Release notes alone (the alpha process, October 18) -------------------------


def _on(text: str) -> str:
    """A workflow's `on:` block."""
    return text[text.index("\non:\n") : text.index("\n\n", text.index("\non:\n") + 1)]


def test_a_push_of_release_notes_alone_isn_t_built_again():
    """The image is the one already tested at the version's commit, so a
    notes-only push starts no 50-minute run. Only docs/releases/ is left out:
    the rest of docs/ is in the test stage, and tests read it."""
    on = _on(IMAGE.read_text())
    ignored = re.findall(r"paths-ignore: \[(.*)\]", on)
    assert ignored == ['"docs/releases/**"'], on
    assert "branches: [main]" in on and "workflow_dispatch:" in on
    assert not re.search(r"^\s+paths:", on, re.M)  # (nothing else narrows it)


def test_a_push_of_release_notes_starts_the_release_workflow_itself():
    """With no image run to follow, a notes push must start it, or nothing
    is published; image runs still start it too, for a version whose tests
    were running."""
    on = _on(WORKFLOW.read_text())
    assert re.search(r"workflow_run:\n\s+workflows: \[image\]\n\s+types: \[completed\]", on), on
    push = on[on.index("  push:") :]
    assert "branches: [main]" in push and 'paths: ["docs/releases/**"]' in push, on
    assert "workflow_dispatch:" in on


def test_the_notes_words_are_checked_before_anything_is_published():
    text = WORKFLOW.read_text()
    words = text.index("name: Check the notes' words")
    assert words < text.index("name: Publish what's new")
    assert "tests/test_wording.py" in text[words : text.index("name: Publish what's new")]


def test_notes_naming_a_commit_no_image_run_tested_are_refused(run):
    """Notes pushed for a version whose commit was never built and tested
    (the image run skipped, say) publish nothing."""
    said, status, out = run()
    assert status == 1 and not creates(said)
    assert "hasn't tested its commit" in out


def test_a_run_on_a_later_commit_with_code_changed_doesn_t_count(run):
    """A passing run counts for a version only at its commit, or at a later
    one with nothing but release notes changed since."""
    (run.work / "app" / "later.py").write_text("changed = True\n")
    git(run.work, "add", ".")
    git(run.work, "commit", "-q", "-m", "A code change after 1.32.1's notes")
    git(run.work, "update-ref", "refs/remotes/origin/main", "HEAD")
    run.commits["later"] = git(run.work, "rev-parse", "HEAD")
    image_run(run, 9, version="later")
    said, status, out = run()
    assert status == 1 and not creates(said), said + out
    assert "hasn't tested its commit" in out


def test_a_run_on_the_notes_commit_itself_still_counts(run):
    """(The path before: an image run at the notes' own commit, nothing but
    notes since the version's, still publishes it.)"""
    image_run(run, 10)
    runs = run.assets / "runs.json"
    listed = json.loads(runs.read_text())
    listed["workflow_runs"][0]["head_sha"] = git(run.work, "rev-parse", "HEAD")  # (the notes')
    runs.write_text(json.dumps(listed))
    said, status, out = run()
    assert status == 0, said + out
    assert len(creates(said)) == 1


def test_the_words_step_needs_nothing_but_pytest():
    """The final-diff audit: the step's bare environment has only pytest,
    and tests/conftest.py imports httpx and the app, so the step failed on
    every run and nothing could be published."""
    import ast
    import sys

    text = WORKFLOW.read_text()
    step = text[text.index("name: Check the notes' words") : text.index("name: Publish what's new")]
    assert "--noconftest" in step
    tree = ast.parse((ROOT / "tests" / "test_wording.py").read_text())
    imported = {
        (node.module or "").split(".")[0] if isinstance(node, ast.ImportFrom) else a.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for a in (node.names if isinstance(node, ast.Import) else [node])
    }  # fmt: skip
    outside = {m for m in imported if m not in sys.stdlib_module_names and m not in ("pytest", "")}
    assert outside == set(), outside


def test_a_push_with_code_in_it_leaves_publishing_to_its_image_run():
    """The final-diff audit: a push of code and notes started this before
    its image run was listed, and failed red with "hasn't tested its
    commit" (the image run then published it)."""
    text = WORKFLOW.read_text()
    assert "github.event.before" in text and "docs/releases/" in text
    assert re.search(r"if: .*github\.event_name != 'push'.*notes_only", text), "a code push waits"


def test_a_version_never_tested_says_how_to_start_its_tests(run):
    _said, status, out = run()
    assert status == 1
    assert "Run workflow" in out  # (its commit was pushed with [skip ci], say)


def _pushed_step() -> str:
    """The "Was this push release notes alone?" step's script."""
    lines = WORKFLOW.read_text().splitlines()
    start = next(
        i for i, line in enumerate(lines) if "name: Was this push release notes alone?" in line
    )
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run_at + 1]) - len(lines[run_at + 1].lstrip())
    body = []
    for line in lines[run_at + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body) + "\n"


@pytest.mark.parametrize(
    "case, notes_only",
    [("notes", "true"), ("code", "false"), ("unknown after", "false"), ("no before", "true"),
     ("no before, code", "false")],
)  # fmt: skip
def test_whether_a_push_was_notes_alone(tmp_path, case, notes_only):
    """The re-check: a pushed commit missing from the checkout counted as
    notes alone (git's error left nothing to compare), and a notes push
    whose before wasn't fetched (forced) published nothing."""
    work = tmp_path / "work"
    (work / "docs" / "releases").mkdir(parents=True)
    (work / "app").mkdir()
    git(work, "init", "-q", "-b", "main")
    (work / "app" / "a.py").write_text("x = 1\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "code")
    before = git(work, "rev-parse", "HEAD")
    if "code" in case:
        (work / "app" / "a.py").write_text("x = 2\n")
    else:
        (work / "docs" / "releases" / "v9.md").write_text("notes\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "the push")
    after = git(work, "rev-parse", "HEAD")
    if case == "unknown after":
        after = "0" * 39 + "1"
    if case.startswith("no before"):
        before = "0" * 40
    out = tmp_path / "out"
    done = subprocess.run(
        ["bash", "-e", "-c", _pushed_step()], cwd=work, capture_output=True, text=True,
        env={**os.environ, "BEFORE": before, "AFTER": after, "GITHUB_OUTPUT": str(out)},
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert out.read_text().strip() == f"notes_only={notes_only}", done.stdout


def test_a_published_releases_notes_follow_its_notes_file(run):
    """(The owner, October 24: 1.44.0's notes said more of the security tests
    than he wanted.) A release already out keeps its files and its tag, but
    its notes on GitHub follow its notes file when that's changed; one that
    matches is left alone."""
    (run.assets / "published").write_text("v1.32.0\nv1.32.1\n")
    (run.assets / "release_v1.32.0.json").write_text(json.dumps({"id": 50, "body": ""}))
    (run.assets / "release_v1.32.1.json").write_text(
        json.dumps({"id": 51, "body": "The notes, as they were."})
    )
    said, status, out = run()
    assert status == 0, said + out
    edits = [line for line in said.splitlines() if "PATCH" in line]
    assert len(edits) == 1 and "/releases/51 " in edits[0], said
    assert "v1.32.1: its notes on GitHub now match docs/releases/v1.32.1.md" in out
    assert not creates(said) and not publishes(said) and "release delete" not in said
    # (Matching but for GitHub's line ends: left alone.)
    (run.assets / "release_v1.32.1.json").write_text(
        json.dumps({"id": 51, "body": "\r\nThe notes.\r\n"})
    )
    again, status, _ = run()
    assert status == 0 and "PATCH" not in again[len(said) :]


GOOD_MANIFEST = """release = "A patch"
row = 1
class = "B"
features = []

[[review]]
kind = "self-review"
report = "docs/reviews/self.md"
commit = "{commit}"

[modularity]
component = "app/titles.py"
contract = "tests/test_titles.py"
off = "not optional"
deleted = []
"""


def test_from_first_gated_a_version_without_its_manifest_isnt_published(run):
    image_run(run, 7)
    said, status, out = run(FIRST_GATED="1.32.1")
    assert status != 0, said + out
    assert creates(said) == [], said
    assert "release manifest" in out, out


def test_from_first_gated_a_version_with_its_manifest_is_published(run):
    (run.work / "docs" / "reviews").mkdir(parents=True)
    (run.work / "docs" / "reviews" / "self.md").write_text("# Review\n\n## Quality bar\n\nFine.\n")
    (run.work / "docs" / "releases" / "v1.32.2.toml").write_text(
        GOOD_MANIFEST.format(commit=run.commits["1.32.1"])
    )
    run.version("1.32.2")
    image_run(run, 7)
    image_run(run, 8, version="1.32.2")
    said, status, out = run(FIRST_GATED="1.32.2")
    assert status == 0, said + out
    assert any("v1.32.2 --target" in c for c in creates(said)), said


def test_the_release_job_names_its_first_gated_version():
    text = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    ).read_text()
    assert 'FIRST_GATED: "1.44.2"' in text
    assert 'python3 tools/release_gate.py check server "$version" "$commit"' in text
    assert "PLAN_READ_TOKEN: ${{ secrets.PLAN_READ_TOKEN }}" in text


def test_no_workflow_compares_with_a_commit_id():
    """The repository's history starts at 1.44.2: a check compares with a
    release tag, which the history has, never a commit ID from before it."""
    commit = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
    for f in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if re.search(r"\bgit\b", line) and commit.search(line):
                raise AssertionError(f"{f.name}:{n} compares with a commit ID: {line.strip()}")


RETIRED_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIMGwA9MpUzSlWeish/aRH6oYEo3PjkIBC9LXZSXxcdsC"
# 1.44.2's published SHA256SUMS, by its SHA-256 (its signature checked with the retired key that made it).
SUMS_1_44_2 = "bd3f829007c7ff7c8e5e0004e88a6a92abc9e22bd3520a23756403d9cd339ec8"


def test_the_readme_trusts_only_the_current_release_key():
    """release-signing.pub signs from 1.44.3 on, and is the one key the
    README's allowed_signers trusts. 1.44.2 was signed by a key now retired,
    which isn't trusted at all: 1.44.2 is checked by its SHA256SUMS's digest
    (the cold audits of 1.44.3, SO-C1-07 and SO-C2-05)."""
    readme = (ROOT / "README.md").read_text()
    current = " ".join((ROOT / "release-signing.pub").read_text().split()[:2])
    signers = [line for line in readme.splitlines() if 'namespaces="tapioca-release"' in line]
    assert signers == [
        f'tapioca-release namespaces="tapioca-release" {current} tapiOca release signing'
    ]
    assert RETIRED_KEY not in readme
    assert f"`sha256sum SHA256SUMS` must print `{SUMS_1_44_2}`" in readme


def test_the_checks_own_tests_print_as_text(tmp_path):
    """A tool's tests print what the tool prints, ::error:: lines among them:
    GitHub reads that output as text, never as the run's own errors, and a
    failing test still fails the step."""
    text = (ROOT / ".github" / "workflows" / "gates.yml").read_text()
    lines = text.split("- name: The checks' own tests\n", 1)[1].splitlines()
    assert lines[0].strip() == "run: |"
    body = []
    for line in lines[1:]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line[10:])
    script = "\n".join(body)
    names = sorted(set(re.findall(r"tools/test_\w+\.py", script)))
    assert names
    (tmp_path / "tools").mkdir()
    for n in names:
        (tmp_path / n).write_text('print("::error::from a test")\n')
    ran = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    said = ran.stdout.splitlines()
    stops = [s for s in said if s.startswith("::stop-commands::")]
    assert len(stops) == 1
    token = stops[0].removeprefix("::stop-commands::")
    assert len(token) >= 32 and f"::{token}::" in said
    begun, resumed = said.index(stops[0]), said.index(f"::{token}::")
    printed = [i for i, s in enumerate(said) if s == "::error::from a test"]
    assert len(printed) == len(names) and all(begun < i < resumed for i in printed)
    (tmp_path / names[0]).write_text("raise SystemExit(1)\n")
    failed = subprocess.run(
        ["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True
    )
    assert failed.returncode != 0
    assert failed.stdout.splitlines()[-1].startswith("::error::")
