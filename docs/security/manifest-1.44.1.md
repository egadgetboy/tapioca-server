# Security manifest, tapiOca 1.44.1

The six questions every release answers (DL287), for its readiness record.

1. **New or changed routes or parameters?** None.
2. **New outbound request?** None.
3. **New file write or upload?** None.
4. **New use of FFmpeg or another program?** No new program and no new
   input. A copy's filter graph, for picture subtitles only, now fits the
   subtitles' picture into the film's (`scale2ref`'s size, worked out by
   FFmpeg from the two pictures' sizes): nothing in it comes from a file
   name, a request or a person.
5. **New stored field returned to a client?** None.
6. **New dependency?** None.

**What this release's suite doesn't cover** (the residual risk): as
1.44.0's manifest says (slices 2 and 3 of the suite; MED-FFMPEG-01, still a
tracked Medium exception). No external pen test yet.
