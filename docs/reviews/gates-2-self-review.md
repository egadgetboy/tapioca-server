# Gates that enforce themselves, part 2 (the server's side): self-review

Tooling and tests only: nothing tapiOca does changed. October 27 and 28.

## What it built

- **Mutation testing** (`tools/mutate.py`): each small change a bug could
  make to the one viewing decision (`app/viewing.py`: a comparison turned
  around or off by one, `and` for `or`, a condition negated, a constant
  flipped) is made in turn, and the decision's tests run against it; one they
  still pass is a missing test. Weekly in `quality.yml`, in the test image as
  built; a release that changes the decision names its run.
- **The soak with headless clients** (`tests/test_soak_clients.py`): a real
  tapiOca with real FFmpeg, two Stations watched as HLS, Media copies played
  from anywhere with jumps, Media read as the file in ranges, downloads
  dropped part way, and a restart half way. Weekly, and asked for by name.
- **Hard limits** (`tools/limits_baseline.json`): the soak's memory at its
  most and processor time each minute, approved by the owner as the starting
  line (October 28). Beside Jellyfin 10.11.11's image on the same runner, each
  a fresh install with the same Media folder, at rest: 63 MB to Jellyfin's
  150, 0.26 seconds of processor a minute to its 0.22, answering in 4.7
  seconds to its 3.9.
- **The release gate** (`tools/release_gate.py`): from the release after
  1.44.2, a manifest names its limits, its mutation run when it changes the
  decision, and, for the releases that need one, its soak.

## Quality bar

- **What it found:** the first mutation run caught 149 of 171 changes. 16 new
  tests (`tests/test_viewing_decision.py`) pin the 22 rules nothing checked:
  a movie judged by the movie limit and a show by the TV one; a Station whose
  Media folders exactly match a level's is allowed; one an Admin blocked is
  never shown; someone unrestricted sees everything; an episode hidden for
  someone and Clean audio's rule hold even with no limits; each reason a
  Station is hidden, in its order. CI's run of the decision now kills all
  171 (quality.yml, October 28).
- **The soak passed in CI** three times for 30 minutes: about 8,900 ranges
  read, 4,500 copy pieces, 2,700 Station pieces, 444 downloads dropped, a
  restart, and no stall, warning or error; memory 151 MB at most, 71.5
  seconds of processor a minute.
- **Fixed on the way, at the cause:** a mutant whose tests timed out was
  counted as killed without saying so (now said); compiled copies of the
  changed file could run a stale mutant (cleared each time); the soak's
  clients took a restarted stream's pieces for old ones (they tune in afresh,
  as an app does); a passed soak's numbers and a failed gate's reasons reach
  CI's annotations.
- **No new dependency:** standard library only; the tools are in the test
  image's stage, never in what ships.
